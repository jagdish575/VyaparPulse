import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import agent_routes, routes
from app.config import settings
from app.database import SessionLocal, init_db
from app.errors import KiraiError
from app.seed import seed_database

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("kirai")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    with SessionLocal() as db:
        result = seed_database(db)  # no-op when data already exists
    if result.get("seeded"):
        log.info("Database seeded: %s", result)
    if not settings.EURI_API_KEY:
        log.warning("EURI_API_KEY is not set - the AI parser will use the local rule-based fallback.")
    yield


app = FastAPI(title="KirAI API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list({settings.FRONTEND_URL, "http://localhost:3000", "http://127.0.0.1:3000"}),
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_methods=["*"],
    allow_headers=["*"],
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


app.include_router(routes.router)
app.include_router(agent_routes.router)


@app.get("/")
def root():
    return {"name": "KirAI API", "docs": "/docs", "health": "/api/health"}
