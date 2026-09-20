"""Operational safeguards: demo mode gating, reset can never wipe a real store."""
from fastapi.testclient import TestClient

from app.config import settings
from app.database import Base, SessionLocal, engine, init_db
from app.main import app
from app.models import Order, Product
from tests.conftest import sign_in


def _orders(db):
    db.expire_all()
    return db.query(Order).count()


def test_reset_and_seed_are_refused_outside_demo_mode_and_data_survives(client, db, monkeypatch):
    assert client.post("/api/agent/process", json={"message": "2 Maggi bhej do", "customer_id": 1}).json()["success"]
    assert _orders(db) == 1

    sign_in(client, monkeypatch)  # sign in while demo mode is still on, then switch demo mode off
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    for path in ("/api/demo/reset", "/api/seed"):
        res = client.post(path)
        assert res.status_code == 403 and res.json()["detail"]["code"] == "forbidden"
    assert _orders(db) == 1  # nothing was dropped


def test_reset_database_function_itself_refuses(db, monkeypatch):
    """Defence in depth: even a direct call (CLI, script) cannot wipe data outside demo mode."""
    import pytest

    from app.errors import ForbiddenError
    from app.seed import reset_database

    monkeypatch.setattr(settings, "DEMO_MODE", False)
    with pytest.raises(ForbiddenError):
        reset_database()
    assert db.query(Product).count() > 0


def test_startup_seeds_only_in_demo_mode(monkeypatch):
    for demo, expected_seeded in ((False, False), (True, True)):
        Base.metadata.drop_all(bind=engine)
        init_db()
        monkeypatch.setattr(settings, "DEMO_MODE", demo)
        with TestClient(app):  # runs the lifespan (startup)
            pass
        with SessionLocal() as s:
            assert (s.query(Product).count() > 0) is expected_seeded


def test_settings_reports_demo_mode(client, monkeypatch):
    assert client.get("/api/settings").json()["demo_mode"] is True
    sign_in(client, monkeypatch)
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    assert client.get("/api/settings").json()["demo_mode"] is False
