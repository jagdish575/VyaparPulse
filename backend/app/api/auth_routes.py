from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import auth
from app.config import settings
from app.database import get_db
from app.errors import UnauthorizedError, UnavailableError

router = APIRouter(prefix="/api/auth", tags=["auth"])
DB = Annotated[Session, Depends(get_db)]


class LoginIn(BaseModel):
    password: str = Field(min_length=1, max_length=200)


def _cookie_kwargs() -> dict:
    return {
        "httponly": True,
        "secure": settings.COOKIE_SECURE or settings.COOKIE_SAMESITE == "none",
        "samesite": settings.COOKIE_SAMESITE if settings.COOKIE_SAMESITE in ("lax", "strict", "none") else "lax",
        "path": "/",
    }


@router.get("/me")
def me(request: Request, db: DB):
    """Public: tells the frontend whether to show the login screen. Never reveals anything private."""
    mode = auth.auth_mode()
    return {
        "mode": mode,
        "auth_required": mode != "open",
        "authenticated": mode == "open" or auth.session_valid(db, request.cookies.get(auth.COOKIE_NAME)),
    }


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: DB):
    if auth.auth_mode() == "unconfigured":
        raise UnavailableError("Owner login is not configured. Set OWNER_PASSWORD_HASH (python -m app.auth_setup).")
    auth.check_origin(request)
    auth.ensure_not_locked(request)
    stored = auth.configured_hash()
    if not stored:  # open (demo) mode: nothing to log in to
        return {"authenticated": True, "auth_required": False}
    if not auth.verify_password(body.password, stored):
        auth.record_failure(request)
        raise UnauthorizedError("Incorrect password.")
    auth.clear_failures(request)
    token, max_age = auth.create_session(db)
    response.set_cookie(auth.COOKIE_NAME, token, max_age=max_age, **_cookie_kwargs())
    return {"authenticated": True, "auth_required": True}


@router.post("/logout")
def logout(request: Request, response: Response, db: DB):
    auth.check_origin(request)
    auth.end_session(db, request.cookies.get(auth.COOKIE_NAME))
    response.delete_cookie(auth.COOKIE_NAME, path="/")
    return {"authenticated": False}
