"""Owner authentication: private data is unreachable without a session; demo reset can't be triggered anonymously."""
import pytest

from app import auth
from app.config import settings
from app.models import OwnerSession
from tests.conftest import OWNER_PASSWORD, sign_in

FRONTEND = settings.FRONTEND_URL
PRIVATE_GETS = ["/api/orders", "/api/products", "/api/inventory", "/api/customers", "/api/dashboard/stats",
                "/api/activity", "/api/settings", "/api/ledger/summary", "/api/agent/tools", "/api/ai/status"]


@pytest.fixture()
def secured(monkeypatch):
    """A store with an owner password configured and demo mode OFF, like production."""
    monkeypatch.setattr(settings, "OWNER_PASSWORD", OWNER_PASSWORD)
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    auth._failures.clear()


def test_hashing_is_salted_and_verifies():
    a, b = auth.hash_password("a-long-password"), auth.hash_password("a-long-password")
    assert a != b and a.startswith("scrypt$")  # random salt
    assert auth.verify_password("a-long-password", a) and not auth.verify_password("wrong", a)
    assert not auth.verify_password("x", "not-a-valid-hash")


def test_anonymous_callers_cannot_read_private_data(client, secured):
    for path in PRIVATE_GETS:
        res = client.get(path)
        assert res.status_code == 401, path
        assert res.json()["detail"]["code"] == "unauthorized"


def test_anonymous_callers_cannot_mutate_or_trigger_ai_or_reset(client, db, secured):
    calls = [
        ("post", "/api/orders", {"customer_id": 1, "items": [{"product_id": 1, "quantity": 1}]}),
        ("post", "/api/agent/process", {"message": "2 Maggi bhej do", "customer_id": 1}),
        ("post", "/api/demo/reset", None),
        ("post", "/api/seed", None),
        ("post", "/api/ledger/opening", {"amount": "1000"}),
        ("patch", "/api/orders/1/status", {"status": "delivered"}),
    ]
    for method, path, body in calls:
        res = getattr(client, method)(path, json=body) if body is not None else getattr(client, method)(path)
        assert res.status_code == 401, (method, path, res.status_code)
    from app.models import Order, Product

    assert db.query(Order).count() == 0 and db.query(Product).count() > 0  # nothing happened, nothing was dropped


def test_health_and_auth_status_are_public_and_reveal_nothing_private(client, secured):
    health = client.get("/api/health").json()
    assert health["status"] == "ok" and "store" not in health
    me = client.get("/api/auth/me").json()
    assert me == {"mode": "required", "auth_required": True, "authenticated": False}


def test_wrong_password_rejected_then_correct_password_grants_access(client, secured):
    assert client.post("/api/auth/login", json={"password": "nope"}).status_code == 401
    assert client.get("/api/orders").status_code == 401
    ok = client.post("/api/auth/login", json={"password": OWNER_PASSWORD})
    assert ok.status_code == 200
    cookie = ok.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and auth.COOKIE_NAME in cookie
    assert client.get("/api/orders").status_code == 200
    assert client.get("/api/auth/me").json()["authenticated"] is True


def test_only_a_hash_of_the_session_token_is_stored(client, db, secured):
    client.post("/api/auth/login", json={"password": OWNER_PASSWORD})
    token = client.cookies.get(auth.COOKIE_NAME)
    stored = [row.token_hash for row in db.query(OwnerSession)]
    assert token and token not in stored and len(stored) == 1 and len(stored[0]) == 64


def test_logout_ends_the_session_server_side(client, db, secured):
    client.post("/api/auth/login", json={"password": OWNER_PASSWORD})
    token = client.cookies.get(auth.COOKIE_NAME)
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/orders").status_code == 401
    client.cookies.set(auth.COOKIE_NAME, token)  # replaying the old cookie must not work
    assert client.get("/api/orders").status_code == 401
    db.expire_all()
    assert db.query(OwnerSession).count() == 0


def test_expired_session_is_rejected(client, db, secured):
    from datetime import timedelta

    from app.utils import utcnow

    client.post("/api/auth/login", json={"password": OWNER_PASSWORD})
    db.query(OwnerSession).update({"expires_at": utcnow() - timedelta(minutes=1)})
    db.commit()
    assert client.get("/api/orders").status_code == 401


def test_repeated_failures_lock_out_even_the_right_password(client, secured):
    for _ in range(auth.MAX_FAILURES):
        assert client.post("/api/auth/login", json={"password": "wrong"}).status_code == 401
    locked = client.post("/api/auth/login", json={"password": OWNER_PASSWORD})
    assert locked.status_code == 401 and "Too many" in locked.json()["detail"]["message"]


def test_cross_origin_mutation_is_blocked_but_the_real_frontend_works(client, db, secured):
    client.post("/api/auth/login", json={"password": OWNER_PASSWORD})
    body = {"message": "2 Maggi bhej do", "customer_id": 1}
    evil = client.post("/api/agent/process", json=body, headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403
    site = client.post("/api/agent/process", json=body, headers={"Sec-Fetch-Site": "cross-site"})
    assert site.status_code == 403
    good = client.post("/api/agent/process", json=body, headers={"Origin": FRONTEND})
    assert good.status_code == 200 and good.json()["success"]


def test_cors_allows_only_configured_origins_with_credentials(client, secured):
    ok = client.options("/api/orders", headers={"Origin": FRONTEND, "Access-Control-Request-Method": "POST"})
    assert ok.headers.get("access-control-allow-origin") == FRONTEND
    assert ok.headers.get("access-control-allow-credentials") == "true"
    for origin in ("https://evil.example", "https://anything.vercel.app"):
        bad = client.options("/api/orders", headers={"Origin": origin, "Access-Control-Request-Method": "POST"})
        assert "access-control-allow-origin" not in bad.headers


def test_no_password_outside_demo_mode_fails_closed(client, monkeypatch):
    monkeypatch.setattr(settings, "OWNER_PASSWORD", "")
    monkeypatch.setattr(settings, "OWNER_PASSWORD_HASH", "")
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    assert client.get("/api/orders").status_code == 503
    assert client.post("/api/auth/login", json={"password": "anything"}).status_code == 503
    assert client.get("/api/health").status_code == 200  # liveness stays public


def test_demo_mode_without_a_password_stays_open_for_local_use(client):
    assert client.get("/api/auth/me").json() == {"mode": "open", "auth_required": False, "authenticated": True}
    assert client.get("/api/orders").status_code == 200


def test_stored_hash_setting_is_used_and_plain_password_is_not_required(client, monkeypatch):
    monkeypatch.setattr(settings, "OWNER_PASSWORD_HASH", auth.hash_password("only-the-hash-is-stored"))
    monkeypatch.setattr(settings, "OWNER_PASSWORD", "")
    assert client.post("/api/auth/login", json={"password": "only-the-hash-is-stored"}).status_code == 200
    assert client.get("/api/orders").status_code == 200


def test_reset_needs_both_the_owner_and_demo_mode(client, monkeypatch):
    sign_in(client, monkeypatch)
    assert client.post("/api/demo/reset").status_code == 200  # owner + demo mode
    assert client.get("/api/orders").status_code == 200  # reset must not sign the owner out
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    assert client.post("/api/demo/reset").status_code == 403  # owner but not demo mode
