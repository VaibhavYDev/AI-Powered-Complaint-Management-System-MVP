import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from .ai.llm import AIConfigError, AIOutputError, AIProviderError, model_status, resolve_model
from .ai.nodes import NoComplaintToEdit, NothingExtracted
from .api.complaints import router
from .config import settings
from .db import Base, engine
from .documents import DocumentError
from . import models  # noqa: F401  (registers the table on Base)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    resolve_model()
    yield


app = FastAPI(title="AIVOA Complaint Co-pilot", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_methods=["*"],
    allow_headers=["*"],
)
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


@app.get("/api/health")
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("select 1"))
        database = "ok"
    except OperationalError:
        database = "unavailable"
    return {"database": database, "groq_configured": bool(settings.groq_api_key), **model_status()}
