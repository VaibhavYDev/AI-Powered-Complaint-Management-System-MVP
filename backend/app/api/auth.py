from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import crud
from ..auth import (
    client_key,
    clear_session,
    current_user,
    hash_password,
    issue_session,
    session_limiter,
    verify_password,
)
from ..db import get_db
from ..models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    # bcrypt ignores anything past 72 bytes, so refuse longer rather than silently truncate.
    password: str = Field(min_length=10, max_length=72)


class Identity(BaseModel):
    id: int
    email: str | None
    anonymous: bool
    csrf_token: str | None = None


def identity(user: User, csrf: str | None = None) -> Identity:
    return Identity(id=user.id, email=user.email, anonymous=user.email is None, csrf_token=csrf)


@router.get("/me", response_model=Identity)
def me(request: Request, user: User = Depends(current_user)):
    from ..auth import SESSION_COOKIE, read_session

    session = read_session(request.cookies.get(SESSION_COOKIE)) or {}
    return identity(user, session.get("csrf"))


@router.post("/anonymous", response_model=Identity)
def start_anonymous_session(request: Request, response: Response, db: Session = Depends(get_db)):
    """A workspace for a visitor who has not signed up. Its records are private to this session."""
    session_limiter.check(client_key(request))
    user = crud.create_user(db)
    return identity(user, issue_session(response, user))


@router.post("/register", response_model=Identity)
def register(
    body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)
):
    session_limiter.check(client_key(request))
    if crud.user_by_email(db, body.email.lower()):
        raise HTTPException(409, "An account with that email already exists.")
    user = crud.create_user(db, email=body.email.lower(), password_hash=hash_password(body.password))
    return identity(user, issue_session(response, user))


@router.post("/login", response_model=Identity)
def login(body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    session_limiter.check(client_key(request))
    user = crud.user_by_email(db, body.email.lower())
    if user is None or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password.")
    return identity(user, issue_session(response, user))


@router.post("/logout", status_code=204)
def logout(response: Response, user: User = Depends(current_user)):
    clear_session(response)
