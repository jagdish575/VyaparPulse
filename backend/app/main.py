import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import auth
from app.api import agent_routes, auth_routes, ledger_routes, routes
from app.config import settings
from app.database import SessionLocal, init_db
from app.errors import KiraiError
from app.seed import seed_database

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("kirai")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    if settings.DEMO_MODE:  # never populate a real store with fictitious orders
        with SessionLocal() as db:
            result = seed_database(db)  # no-op when data already exists
        if result.get("seeded"):
            log.info("Demo database seeded: %s", result)
    else:
        log.info("DEMO_MODE is off: no demo data is created and demo reset/seed are disabled.")
    if not settings.EURI_API_KEY:
        log.warning("EURI_API_KEY is not set - the AI parser will use the local rule-based fallback.")
    yield


app = FastAPI(title="KirAI API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=auth.allowed_origins(),  # exact origins only (no wildcard): cookies are sent to this list
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Idempotency-Key"],
)


def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": {"code": code, "message": message}})


@app.exception_handler(KiraiError)
async def kirai_error_handler(_req: Request, exc: KiraiError):
    return _err(exc.status_code, exc.code, exc.message)


@app.exception_handler(RequestValidationError)
async def validation_handler(_req: Request, exc: RequestValidationError):
    return _err(422, "invalid_request", "Please check the request and try again.")


@app.exception_handler(StarletteHTTPException)
async def http_handler(_req: Request, exc: StarletteHTTPException):
    return _err(exc.status_code, "http_error", "That request could not be completed.")


@app.exception_handler(Exception)
async def unhandled_handler(_req: Request, exc: Exception):
    log.exception("Unhandled error", exc_info=exc)
    return _err(500, "server_error", "Something went wrong on our side. Please try again.")


# Public: liveness + login. Everything else needs the store owner's session (see app/auth.py).
app.include_router(routes.public_router)
app.include_router(auth_routes.router)
_private = [Depends(auth.require_owner)]
app.include_router(routes.router, dependencies=_private)
app.include_router(agent_routes.router, dependencies=_private)
app.include_router(ledger_routes.router, dependencies=_private)


@app.get("/")
def root():
    return {"name": "KirAI API", "docs": "/docs", "health": "/api/health"}
