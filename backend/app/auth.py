"""Session identity and per-request authorization.

Every complaint belongs to exactly one principal. A visitor gets an anonymous workspace so
the demo needs no sign-up; a named account lets the same workspace be reached again later.
Either way the session is a signed, HttpOnly cookie and the owner is taken from that cookie,
never from the request body.
"""

import logging
import secrets
import time
from collections import defaultdict, deque

import bcrypt
from fastapi import Cookie, Depends, HTTPException, Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User

log = logging.getLogger(__name__)

SESSION_COOKIE = "aivoa_session"
CSRF_HEADER = "X-CSRF-Token"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
MAX_PASSWORD_BYTES = 72  # bcrypt truncates beyond this

_secret = settings.session_secret or secrets.token_urlsafe(32)
if not settings.session_secret:
    log.warning("SESSION_SECRET is not set; sessions will not survive a restart or a second instance")
_serializer = URLSafeTimedSerializer(_secret, salt="aivoa-session")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def issue_session(response: Response, user: User) -> str:
    """Sign the user id into the cookie and return the CSRF token the client must echo."""
    csrf = secrets.token_urlsafe(16)
    response.set_cookie(
        SESSION_COOKIE,
        _serializer.dumps({"uid": user.id, "csrf": csrf}),
        max_age=settings.session_max_age,
        httponly=True,
        samesite="lax",
        secure=settings.secure_cookies,
        path="/",
    )
    return csrf


def clear_session(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="lax", secure=settings.secure_cookies)


def read_session(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        return _serializer.loads(raw, max_age=settings.session_max_age)
    except (BadSignature, SignatureExpired):
        return None


def current_user(
    request: Request,
    db: Session = Depends(get_db),
    aivoa_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> User:
    """The authenticated principal, or 401. Also enforces CSRF on state-changing requests."""
    session = read_session(aivoa_session)
    if not session:
        raise HTTPException(401, "Sign in to continue.")
    user = db.get(User, session["uid"])
    if user is None:
        raise HTTPException(401, "Sign in to continue.")
    if request.method in UNSAFE_METHODS and request.headers.get(CSRF_HEADER) != session["csrf"]:
        raise HTTPException(403, "Missing or invalid CSRF token.")
    return user


class RateLimiter:
    """Fixed-window limiter held in process memory. With more than one instance the effective
    allowance is per instance; it exists to stop a single visitor hammering the model API."""

    def __init__(self, limit: int, window: float):
        self.limit, self.window = limit, window
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            raise HTTPException(429, "Too many requests; please wait a moment.")
        hits.append(now)


ai_limiter = RateLimiter(settings.ai_rate_limit, settings.ai_rate_window)
session_limiter = RateLimiter(settings.session_rate_limit, settings.session_rate_window)


def limit_ai(user: User = Depends(current_user)) -> User:
    ai_limiter.check(str(user.id))
    return user


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"
