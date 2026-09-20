"""Single-store-owner authentication.

- The password is stored only as a salted scrypt hash (OWNER_PASSWORD_HASH). Generate one with:
      python -m app.auth_setup
  OWNER_PASSWORD (plain) is accepted for quick local demos only.
- Login creates a random server-side session. Only its SHA-256 is stored; the browser gets an HttpOnly cookie.
- Modes (see auth_mode):
    required      a password is configured        -> every /api route except health/auth needs a session
    open          DEMO_MODE and no password       -> no login (local demo convenience)
    unconfigured  no password and not demo mode   -> protected routes answer 503 (fail closed, never open by accident)
"""
import base64
import hashlib
import hmac
import secrets
import time
from datetime import timedelta
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.errors import ForbiddenError, UnauthorizedError, UnavailableError
from app.models import OwnerSession
from app.utils import utcnow

COOKIE_NAME = "kirai_session"
_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}
MIN_PASSWORD_LENGTH = 10


# ----------------------------------------------------------------------------- password hashing

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return "scrypt${}${}${}${}${}".format(
        _SCRYPT["n"], _SCRYPT["r"], _SCRYPT["p"],
        base64.b64encode(salt).decode(), base64.b64encode(digest).decode(),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest_b64)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64),
                                n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


@lru_cache(maxsize=4)
def _hash_plain(plain: str) -> str:
    return hash_password(plain)


def configured_hash() -> str | None:
    if settings.OWNER_PASSWORD_HASH:
        return settings.OWNER_PASSWORD_HASH
    if settings.OWNER_PASSWORD:
        return _hash_plain(settings.OWNER_PASSWORD)
    return None


def auth_mode() -> str:
    if configured_hash():
        return "required"
    return "open" if settings.DEMO_MODE else "unconfigured"


# ----------------------------------------------------------------------------- origins / CSRF

def allowed_origins() -> list[str]:
    origins = {settings.FRONTEND_URL.rstrip("/"), *settings.EXTRA_ORIGINS}
    if settings.DEMO_MODE:  # local development conveniences only
        origins |= {"http://localhost:3000", "http://127.0.0.1:3000"}
    return sorted(o for o in origins if o)


def check_origin(request: Request) -> None:
    """CSRF defence for cookie sessions: a state-changing request from a browser must come from our frontend.
    Non-browser clients (curl, tests) send no Origin and are not CSRF vectors, so they pass."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    origin = request.headers.get("origin")
    if origin is not None:
        if origin.rstrip("/") not in allowed_origins():
            raise ForbiddenError("This request came from an origin that is not allowed.")
    elif request.headers.get("sec-fetch-site") == "cross-site":
        raise ForbiddenError("This request came from an origin that is not allowed.")


# ----------------------------------------------------------------------------- brute-force protection

MAX_FAILURES = 5
LOCKOUT_SECONDS = 300
_failures: dict[str, list[float]] = {}  # per client address; in-memory (single process)


def _client_id(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _recent_failures(client: str) -> list[float]:
    cutoff = time.monotonic() - LOCKOUT_SECONDS
    recent = [t for t in _failures.get(client, []) if t > cutoff]
    _failures[client] = recent
    return recent


def ensure_not_locked(request: Request) -> None:
    if len(_recent_failures(_client_id(request))) >= MAX_FAILURES:
        raise UnauthorizedError("Too many failed sign-in attempts. Please wait a few minutes and try again.")


def record_failure(request: Request) -> None:
    _failures.setdefault(_client_id(request), []).append(time.monotonic())


def clear_failures(request: Request) -> None:
    _failures.pop(_client_id(request), None)


# ----------------------------------------------------------------------------- sessions

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session) -> tuple[str, int]:
    """Returns (raw token for the cookie, lifetime in seconds)."""
    now = utcnow()
    db.execute(delete(OwnerSession).where(OwnerSession.expires_at < now))  # drop expired sessions
    token = secrets.token_urlsafe(32)
    ttl = timedelta(hours=settings.SESSION_TTL_HOURS)
    db.add(OwnerSession(token_hash=_token_hash(token), created_at=now, expires_at=now + ttl))
    db.commit()
    return token, int(ttl.total_seconds())


def session_valid(db: Session, token: str | None) -> bool:
    if not token:
        return False
    row = db.get(OwnerSession, _token_hash(token))
    return row is not None and row.expires_at > utcnow()


def end_session(db: Session, token: str | None) -> None:
    if token:
        db.execute(delete(OwnerSession).where(OwnerSession.token_hash == _token_hash(token)))
        db.commit()


# ----------------------------------------------------------------------------- dependency

def require_owner(request: Request, db: Annotated[Session, Depends(get_db)]) -> None:
    """Guard for every private route (orders, inventory, customers, ledger, AI, settings...)."""
    mode = auth_mode()
    if mode == "open":
        return
    if mode == "unconfigured":
        raise UnavailableError("Owner login is not configured. Set OWNER_PASSWORD_HASH (python -m app.auth_setup).")
    check_origin(request)
    if not session_valid(db, request.cookies.get(COOKIE_NAME)):
        raise UnauthorizedError("Please sign in to continue.")
