"""Central configuration. Secrets come from the environment only (never hardcoded)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")  # does not override variables already set in the environment


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


def _flag(name: str, default: bool = False) -> bool:
    return _env(name, "true" if default else "false").lower() in ("1", "true", "yes", "on")


class Settings:
    # --- EURI (OpenAI-compatible gateway) ---
    EURI_API_KEY: str = _env("EURI_API_KEY")
    EURI_BASE_URL: str = _env("EURI_BASE_URL", "https://api.euron.one/api/v1/euri").rstrip("/")
    EURI_MODEL: str = _env("EURI_MODEL", "gpt-4.1-nano")
    # Max wait for one EURI call. If EURI is slower, the agent falls back to the local parser (and says so).
    EURI_TIMEOUT_SECONDS: float = float(_env("EURI_TIMEOUT_SECONDS", "8"))

    # --- Database ---
    DATABASE_URL: str = _env("DATABASE_URL", f"sqlite:///{(BASE_DIR / 'kirai.db').as_posix()}")

    # --- Web ---
    FRONTEND_URL: str = _env("FRONTEND_URL", "http://localhost:3000")
    # Extra browser origins allowed to call the API (comma separated). Exact origins only - no wildcards.
    EXTRA_ORIGINS: list[str] = [o.strip().rstrip("/") for o in _env("EXTRA_ORIGINS").split(",") if o.strip()]

    # --- Demo mode ---
    # OFF by default. Demo mode enables: seeding fictitious data on startup, POST /api/seed and POST /api/demo/reset
    # (which DROPS every table, including the financial ledger). Never enable it for a store with real records.
    DEMO_MODE: bool = _flag("DEMO_MODE", False)

    # --- Owner login (single store owner) ---
    # Store ONLY a hash (python -m app.auth_setup prints one). OWNER_PASSWORD (plain) is accepted for quick demos.
    OWNER_PASSWORD_HASH: str = _env("OWNER_PASSWORD_HASH")
    OWNER_PASSWORD: str = _env("OWNER_PASSWORD")
    SESSION_TTL_HOURS: int = int(_env("SESSION_TTL_HOURS", "12"))
    # Cross-site deployments (Vercel frontend + separate API host) need COOKIE_SAMESITE=none and COOKIE_SECURE=true.
    COOKIE_SAMESITE: str = _env("COOKIE_SAMESITE", "lax").lower()
    COOKIE_SECURE: bool = _flag("COOKIE_SECURE", False)

    # --- Store rules ---
    STORE_NAME: str = _env("STORE_NAME", "Sharma Kirana Store")
    STORE_LOCATION: str = _env("STORE_LOCATION", "Vijay Nagar, Indore")
    DELIVERY_CHARGE: float = float(_env("DELIVERY_CHARGE", "30"))
    FREE_DELIVERY_ABOVE: float = float(_env("FREE_DELIVERY_ABOVE", "999"))
    MAX_QTY_PER_ITEM: int = int(_env("MAX_QTY_PER_ITEM", "50"))
    DEMO_CUSTOMER_ID: int = 1


settings = Settings()
