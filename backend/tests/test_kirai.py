"""KirAI backend tests: matching, inventory, order transaction, agent workflow, edge cases, reset."""
import json

import pytest

from app.ai.agent import process_message
from app.ai.euri_client import EuriClient, EuriError
from app.ai.parser import fallback_parse, parse_message
from app.errors import InsufficientStockError
from app.models import ActivityLog, InventoryLog, Order, OrderItem
from app.schemas import AgentRequest
from app.services import inventory_service, order_service
from tests.conftest import set_stock, stock_of

DEMO_MESSAGE = "Bhaiya 2 packets Aashirvaad atta, 1 Fortune oil aur 3 Maggi bhej do. Ghar pe deliver kar dena."
MAGGI, ATTA, SUNFLOWER = "Maggi 70g", "Aashirvaad Atta 5kg", "Fortune Sunflower Oil 1L"


def ask(db, message, draft=None, customer_id=1):
    return process_message(db, AgentRequest(message=message, customer_id=customer_id, draft=draft))


def pid(db, name):
    return next(p.id for p in inventory_service.list_products(db) if p.name == name)


# ------------------------------------------------------------------ product search & matching

def test_product_search(db):
    assert inventory_service.search_products(db, "atta")[0].name == ATTA
    assert inventory_service.search_products(db, "maggi")[0].name == MAGGI
    assert inventory_service.search_products(db, "sarso")[0].name == "Fortune Mustard Oil 1L"
    assert inventory_service.search_products(db, "aashirwad atta")[0].name == ATTA  # typo tolerant
    assert inventory_service.search_products(db, "zzzz") == []


def test_resolution_matched_ambiguous_not_found(db):
    assert inventory_service.resolve_product(db, "Aashirvaad atta").product.name == ATTA
    assert inventory_service.resolve_product(db, "Fortune oil").product.name == SUNFLOWER

    oil = inventory_service.resolve_product(db, "oil")
    assert oil.status == "ambiguous"
    assert {p.name for p in oil.options} == {SUNFLOWER, "Fortune Mustard Oil 1L"}

    oreo = inventory_service.resolve_product(db, "Oreo", category_hint="biscuits")
    assert oreo.status == "not_found"
    assert "Parle-G Biscuits" in [p.name for p in oreo.suggestions]


# ------------------------------------------------------------------ inventory lookup

def test_inventory_lookup(db):
    set_stock(db, MAGGI, 10)
    inv = inventory_service.get_inventory(db, pid(db, MAGGI))
    assert inv["stock_quantity"] == 10 and inv["price"] == 14
    assert inv["status"] == "low_stock"  # Maggi's low-stock threshold is 15
    set_stock(db, MAGGI, 40)
    assert inventory_service.get_inventory(db, pid(db, MAGGI))["status"] == "in_stock"
    assert inventory_service.get_inventory(db, pid(db, "Pepsi 750ml"))["status"] == "out_of_stock"


def test_inventory_api(client):
    data = client.get("/api/inventory").json()
    assert data["summary"]["total_products"] >= 20
    assert len(data["products"]) == data["summary"]["total_products"]
    low = client.get("/api/inventory?status=out_of_stock").json()["products"]
    assert [p["name"] for p in low] == ["Pepsi 750ml"]


# ------------------------------------------------------------------ order totals & deduction

def test_order_total_and_delivery_rules(db):
    items = [{"product_id": pid(db, ATTA), "quantity": 2}, {"product_id": pid(db, SUNFLOWER), "quantity": 1},
             {"product_id": pid(db, MAGGI), "quantity": 3}]
    quote = order_service.calculate_order(db, items, delivery=True)
    assert (quote.subtotal, quote.delivery_charge, quote.total) == (707, 30, 737)
    assert order_service.calculate_order(db, items, delivery=False).total == 707
    big = order_service.calculate_order(db, [{"product_id": pid(db, "Daawat Basmati Rice 5kg"), "quantity": 2}])
    assert big.delivery_charge == 0  # free delivery above the threshold


def test_inventory_deduction(db):
    set_stock(db, MAGGI, 10)
    result = order_service.create_order(db, 1, [{"product_id": pid(db, MAGGI), "quantity": 3}], "Vijay Nagar, Indore")
    assert stock_of(db, MAGGI) == 7
    log = db.query(InventoryLog).one()
    assert (log.order_id, log.quantity_change, log.stock_before, log.stock_after) == (result.order.id, -3, 10, 7)
    assert db.query(ActivityLog).filter_by(order_id=result.order.id).count() == 2  # created + inventory updated


def test_update_inventory_is_idempotent(db):
    set_stock(db, MAGGI, 10)
    result = order_service.create_order(db, 1, [{"product_id": pid(db, MAGGI), "quantity": 3}])
    order_service.update_inventory(db, result.order.id)
    assert stock_of(db, MAGGI) == 7  # not deducted twice


def test_stock_never_goes_negative(db):
    set_stock(db, MAGGI, 4)
    with pytest.raises(InsufficientStockError):
        order_service.create_order(db, 1, [{"product_id": pid(db, MAGGI), "quantity": 10}])
    assert stock_of(db, MAGGI) == 4 and db.query(Order).count() == 0


def test_transaction_rollback_leaves_nothing_behind(db, monkeypatch):
    """If anything fails mid-transaction (2nd item's deduction), the order, items, logs and the FIRST
    item's stock deduction must all be rolled back."""
    set_stock(db, MAGGI, 10)
    set_stock(db, ATTA, 10)
    real, calls = inventory_service.deduct_stock, {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated crash mid-transaction")
        return real(*args, **kwargs)

    monkeypatch.setattr(inventory_service, "deduct_stock", flaky)
    with pytest.raises(RuntimeError):
        order_service.create_order(db, 1, [{"product_id": pid(db, MAGGI), "quantity": 3},
                                           {"product_id": pid(db, ATTA), "quantity": 2}])
    db.expire_all()
    assert calls["n"] == 2
    assert db.query(Order).count() == 0 and db.query(OrderItem).count() == 0
    assert db.query(InventoryLog).count() == 0 and db.query(ActivityLog).count() == 0
    assert stock_of(db, MAGGI) == 10 and stock_of(db, ATTA) == 10


# ------------------------------------------------------------------ full agent workflow

def test_main_demo_request_end_to_end(db):
    before = {n: stock_of(db, n) for n in (ATTA, SUNFLOWER, MAGGI)}
    res = ask(db, DEMO_MESSAGE)

    assert res.success and res.status == "confirmed" and res.intent == "place_order"
    assert [s.name for s in res.steps] == ["parse_request", "find_products", "check_inventory", "calculate_total",
                                          "create_order", "update_inventory", "send_confirmation"]
    assert all(s.status == "completed" for s in res.steps)
    assert (res.order.subtotal, res.order.delivery_charge, res.order.total) == (707, 30, 737)
    assert res.order.customer.name == "Rahul Sharma" and res.order.delivery_address == "Vijay Nagar, Indore"
    assert sorted((i.product_name, i.quantity, i.line_total) for i in res.order.items) == sorted(
        [(ATTA, 2, 520), (SUNFLOWER, 1, 145), (MAGGI, 3, 42)])

    # real database side effects
    assert stock_of(db, ATTA) == before[ATTA] - 2
    assert stock_of(db, SUNFLOWER) == before[SUNFLOWER] - 1
    assert stock_of(db, MAGGI) == before[MAGGI] - 3
    assert db.query(Order).count() == 1 and db.query(InventoryLog).count() == 3
    actions = [a.action for a in db.query(ActivityLog).filter_by(order_id=res.order.id).order_by(ActivityLog.id)]
    assert actions == ["request_parsed", "products_matched", "inventory_verified", "prices_verified",
                       "order_created", "inventory_updated", "confirmation_sent"]


def test_main_demo_works_repeatedly(db):
    for _ in range(3):
        assert ask(db, DEMO_MESSAGE).order.total == 737


def test_unknown_product_creates_no_order(db):
    res = ask(db, "2 Oreo bhej do")
    assert not res.success and res.status == "rejected"
    assert "couldn't find Oreo in the store inventory" in res.reply
    assert "Parle-G Biscuits" in res.reply  # similar product suggested
    assert res.steps[1].status == "failed" and all(s.status == "skipped" for s in res.steps[2:])
    assert db.query(Order).count() == 0 and db.query(InventoryLog).count() == 0


def test_insufficient_stock_creates_no_order(db):
    set_stock(db, MAGGI, 4)
    res = ask(db, "10 Maggi bhej do")
    assert not res.success and res.status == "rejected"
    assert "Only 4 Maggi 70g are currently available" in res.reply and "haven't placed the order yet" in res.reply
    assert db.query(Order).count() == 0 and stock_of(db, MAGGI) == 4


def test_out_of_stock_product_rejected(db):
    res = ask(db, "1 Pepsi bhej do")
    assert res.status == "rejected" and "out of stock" in res.reply and db.query(Order).count() == 0


def test_ambiguous_product_asks_then_completes(db):
    res = ask(db, "1 oil bhejo")
    assert res.status == "needs_clarification" and not res.success
    assert "Which oil would you like?" in res.reply
    assert [o.name for o in res.clarification.options] == ["Fortune Mustard Oil 1L", SUNFLOWER]
    assert db.query(Order).count() == 0  # never guesses

    follow_up = ask(db, "sunflower", draft=res.draft)  # customer picks
    assert follow_up.status == "confirmed" and follow_up.order.items[0].product_name == SUNFLOWER
    assert follow_up.order.subtotal == 145

    by_number = ask(db, "2", draft=res.draft)  # or by number
    assert by_number.order.items[0].product_name == SUNFLOWER


def test_unrelated_reply_to_clarification_starts_fresh(db):
    res = ask(db, "1 oil bhejo")
    fresh = ask(db, "2 Maggi bhej do", draft=res.draft)
    assert fresh.status == "confirmed" and fresh.order.items[0].product_name == MAGGI


def test_empty_request(db):
    res = ask(db, "   ")
    assert res.status == "needs_input" and res.reply == "What would you like to order?"
    assert ask(db, "bhaiya bhej do").reply == "What would you like to order?"


def test_mixed_valid_and_invalid_items_places_nothing(db):
    res = ask(db, "2 Maggi aur 1 Oreo bhej do")
    assert res.status == "rejected" and db.query(Order).count() == 0 and stock_of(db, MAGGI) == 60


def test_invalid_quantity_rejected(db):
    res = ask(db, "500 Maggi bhej do")
    assert res.status == "rejected" and db.query(Order).count() == 0


def test_stock_query_and_low_stock(db):
    res = ask(db, "bhaiya atta khatam ho gaya kya?")
    assert res.intent == "check_stock" and res.success and "Aashirvaad Atta 5kg: 40 in stock" in res.reply
    low = ask(db, "Show low stock")
    assert low.intent == "low_stock" and "Pepsi 750ml: out of stock" in low.reply
    assert db.query(Order).count() == 0


# ------------------------------------------------------------------ Hinglish understanding (local parser)

@pytest.mark.parametrize("text,expected", [
    ("2 Maggi aur ek atta bhej do", [("maggi", 2), ("atta", 1)]),
    ("bhaiya 1 litre oil aur 2 packet biscuit dena", [("oil", 1), ("biscuit", 2)]),
    ("mujhe 3 Maggi chahiye", [("maggi", 3)]),
    ("aur 2 Amul milk bhi add kar do", [("amul milk", 2)]),
    ("mere ghar 2 packet chips bhejna", [("chips", 2)]),
    ("do maggi bhej do", [("maggi", 2)]),
    ("I want 4 Parle-G", [("parle", 4)]),
])
def test_hinglish_parsing(text, expected):
    parsed = fallback_parse(text)
    assert parsed.intent == "place_order"
    assert [(i.name, i.quantity) for i in parsed.items] == expected


def test_hinglish_intents():
    assert fallback_parse("bhaiya atta khatam ho gaya kya?").intent == "check_stock"
    assert fallback_parse("Check atta stock").intent == "check_stock"
    assert fallback_parse("Show low stock").intent == "low_stock"
    assert fallback_parse("hello").intent == "other"
    assert fallback_parse("ghar pe deliver kar dena").delivery is True


# ------------------------------------------------------------------ EURI integration (mocked HTTP layer)

class FakeEuri(EuriClient):
    def __init__(self, reply=None, fail=False):
        super().__init__(api_key="test-key", base_url="http://euri.invalid", model="test-model")
        self._reply, self._fail = reply, fail

    def chat(self, messages, temperature=0.2, max_tokens=700):
        if self._fail:
            raise EuriError("EURI returned HTTP 500")
        return self._reply


def test_euri_structured_output_is_used_and_validated():
    payload = {"intent": "place_order", "items": [{"name": "Maggi", "quantity": "3", "category_hint": "noodles"}],
               "delivery": True, "delivery_address": None, "language": "hinglish"}
    client = FakeEuri(reply="```json\n" + json.dumps(payload) + "\n```")  # fenced JSON must still parse
    parsed, info = parse_message(client, "3 maggi bhej do")
    assert info.provider == "euri" and info.model == "test-model"
    assert parsed.items[0].quantity == 3


def test_euri_failure_falls_back_to_local_parser_transparently(db):
    res = process_message(db, AgentRequest(message="3 Maggi bhej do", customer_id=1), FakeEuri(fail=True))
    assert res.parser.provider == "local" and "HTTP 500" in res.parser.note
    assert res.status == "confirmed"


def test_euri_timeout_falls_back_quickly_and_is_not_retried(db):
    from app.ai.euri_client import EuriTimeout

    class Slow(FakeEuri):
        calls = 0

        def chat(self, messages, temperature=0.2, max_tokens=700):
            Slow.calls += 1
            raise EuriTimeout("EURI did not respond within 8s")

    res = process_message(db, AgentRequest(message="3 Maggi bhej do", customer_id=1), Slow())
    assert Slow.calls == 1  # no retry storm: the demo must not stall
    assert res.parser.provider == "local" and "did not respond" in res.parser.note
    assert res.status == "confirmed"


def test_euri_hard_deadline_even_if_the_http_call_hangs(monkeypatch):
    """httpx timeouts are per-socket-read; a slow gateway must still not stall us past the deadline."""
    import time

    import httpx

    from app.ai.euri_client import EuriTimeout

    monkeypatch.setattr(httpx, "post", lambda *a, **k: time.sleep(3))
    client = EuriClient(api_key="test-key", base_url="http://euri.invalid", timeout=0.4)
    started = time.perf_counter()
    with pytest.raises(EuriTimeout):
        client.chat([{"role": "user", "content": "hi"}])
    assert time.perf_counter() - started < 1.5


def test_euri_result_is_cached_for_identical_message():
    payload = {"intent": "place_order", "items": [{"name": "Maggi", "quantity": 3}], "delivery": True}
    first = FakeEuri(reply=json.dumps(payload))
    parse_message(first, "3 Maggi bhej do")

    class Boom(FakeEuri):
        def chat(self, *a, **k):
            raise AssertionError("EURI should not be called again for a cached message")

    parsed, info = parse_message(Boom(), "  3 maggi  BHEJ do ")
    assert info.provider == "euri" and info.note == "cached EURI result" and parsed.items[0].quantity == 3


def test_euri_garbage_output_falls_back():
    parsed, info = parse_message(FakeEuri(reply="sure! here you go"), "2 maggi bhej do")
    assert info.provider == "local" and parsed.items[0].name == "maggi"


def test_ai_cannot_set_prices_or_stock(db):
    """Even if the model returns extra price/order fields, only DB-verified values are used."""
    payload = {"intent": "place_order", "items": [{"name": "Maggi", "quantity": 3, "price": 1, "order_id": 999}],
               "delivery": False}
    res = process_message(db, AgentRequest(message="3 maggi", customer_id=1), FakeEuri(reply=json.dumps(payload)))
    assert res.order.subtotal == 42 and res.order.id != 999 and res.order.delivery_charge == 0


# ------------------------------------------------------------------ HTTP API

def test_api_agent_process_and_readback(client):
    res = client.post("/api/agent/process", json={"message": DEMO_MESSAGE, "customer_id": 1,
                                                  "delivery_address": "Vijay Nagar, Indore"})
    assert res.status_code == 200
    body = res.json()
    assert body["success"] and body["order"]["total"] == 737 and body["steps"][0]["timestamp"].endswith("Z")

    order = client.get(f"/api/orders/{body['order']['id']}").json()
    assert order["customer"]["name"] == "Rahul Sharma" and len(order["activity"]) == 7
    assert len(order["inventory_changes"]) == 3
    assert client.get("/api/dashboard/stats").json()["orders_today"] == 1
    customers = client.get("/api/customers").json()
    assert customers[0]["orders_count"] == 1 and customers[0]["total_spent"] == 737
    assert client.get("/api/customers/1").json()["orders"][0]["id"] == body["order"]["id"]
    assert client.get("/api/activity").json()[0]["order_id"] == body["order"]["id"]


def test_api_validation_and_friendly_errors(client):
    bad = client.post("/api/orders", json={"customer_id": 1, "items": [{"product_id": 1, "quantity": -3}]})
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "invalid_request"
    missing = client.get("/api/orders/99999")
    assert missing.status_code == 404 and "could not be found" in missing.json()["detail"]["message"]
    assert client.get("/api/products/search?q=maggi").json()[0]["name"] == MAGGI
    assert client.get("/api/health").json()["status"] == "ok"


def test_api_manual_order_and_insufficient_stock(client, db):
    ok = client.post("/api/orders", json={"customer_id": 1, "items": [{"product_id": pid(db, MAGGI), "quantity": 2}]})
    assert ok.status_code == 201 and ok.json()["total"] == 58
    too_many = client.post("/api/orders", json={"customer_id": 1, "items": [{"product_id": pid(db, "Pepsi 750ml"), "quantity": 1}]})
    assert too_many.status_code == 409


def test_ai_status_never_exposes_key(client):
    body = json.dumps(client.get("/api/ai/status").json()).lower()
    assert "api_key" not in body and "bearer" not in body
    tools = {t["name"] for t in client.get("/api/agent/tools").json()}
    assert {"search_products", "create_order", "update_inventory", "calculate_order"} <= tools
    assert not any("sql" in t for t in tools)


def test_demo_reset_restores_everything(client, db):
    assert client.post("/api/agent/process", json={"message": "5 Maggi bhej do", "customer_id": 1}).json()["success"]
    reset = client.post("/api/demo/reset").json()
    assert reset["success"] and reset["orders"] == 8
    db.expire_all()
    assert inventory_service.get_product(db, pid(db, MAGGI)).stock_quantity == 56  # seed 60 minus seeded history
    first = client.post("/api/agent/process", json={"message": DEMO_MESSAGE, "customer_id": 1}).json()
    assert first["order"]["id"] == 1042 and first["order"]["total"] == 737
