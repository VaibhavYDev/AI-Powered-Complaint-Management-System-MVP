import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from .ai.llm import AIConfigError, AIOutputError, AIProviderError, model_status, resolve_model
from .ai.nodes import NoComplaintToEdit, NothingExtracted
from .api.auth import router as auth_router
from .api.complaints import router
from .config import settings
from .db import engine
from .migrate import upgrade_to_head
from .documents import DocumentError
from . import models  # noqa: F401  (registers the table on Base)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


log = logging.getLogger("app")

# Whether the schema is known to be at head. Startup tries once; if the database was asleep or
# unreachable it is retried on the next health check rather than leaving the service dead.
_schema = {"ready": False, "error": None}


def ensure_schema() -> bool:
    if _schema["ready"]:
        return True
    try:
        upgrade_to_head()
        _schema.update(ready=True, error=None)
    except Exception as exc:  # noqa: BLE001 - the reason is reported, not swallowed
        _schema["error"] = f"{type(exc).__name__}: {exc}"[:200]
        log.error("Schema upgrade failed, serving in a degraded state: %s", _schema["error"])
    return _schema["ready"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Nothing here may raise or block indefinitely. If the database or the model provider is
    # unreachable the process must still bind its port and serve the interface, otherwise the
    # platform router holds every request open and the application looks like it never loads.
    ensure_schema()
    resolve_model()
    yield


app = FastAPI(title="AIVOA Complaint Co-pilot", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(router)

# Expected failures map to HTTP errors here so the endpoints stay free of try/except.
STATUS = {
    NoComplaintToEdit: 400,
    DocumentError: 400,
    NothingExtracted: 422,
    AIOutputError: 502,
    AIProviderError: 502,
    AIConfigError: 503,
    OperationalError: 503,
}


def _handler(status: int):
    async def handle(request: Request, exc: Exception):
        detail = "Database is unavailable." if isinstance(exc, OperationalError) else str(exc)
        return JSONResponse({"detail": detail}, status_code=status)

    return handle


for exc_cls, code in STATUS.items():
    app.add_exception_handler(exc_cls, _handler(code))


_probe = {"at": 0.0, "state": ""}


def database_state() -> str:
    """Briefly cached so that a database which is down cannot also make this endpoint slow."""
    now = time.monotonic()
    if _probe["state"] and now - _probe["at"] < settings.health_cache_seconds:
        return _probe["state"]
    try:
        with engine.connect() as conn:
            conn.execute(text("select 1"))
        state = "ok"
    except OperationalError as exc:
        state = "unavailable"
        log.warning("Health check could not reach the database: %s", type(exc).__name__)
    _probe.update(at=now, state=state)
    return state


@app.get("/api/health")
def health():
    """Liveness: answering at all proves the process is up. The body reports readiness, so an
    unhealthy database is visible rather than disguised as a working application."""
    database = database_state()
    if database == "ok":
        ensure_schema()  # the database may have been asleep when the process started

    return {
        "status": "ready" if database == "ok" and _schema["ready"] else "degraded",
        "database": database,
        "schema": "ready" if _schema["ready"] else "pending",
        "schema_error": _schema["error"],
        "groq_configured": bool(settings.groq_api_key),
        **model_status(),
    }


@app.get("/api/ready")
def ready():
    """Strict readiness for orchestrators: 503 until the application can actually serve."""
    state = health()
    if state["status"] != "ready":
        return JSONResponse(state, status_code=503)
    return state


# Single-container deployment: serve the built React app from the same origin (see Dockerfile).
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
