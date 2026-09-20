"""A retry (lost response, double click, flaky network) must never create a second order or deduct stock twice."""
from concurrent.futures import ThreadPoolExecutor

from app.models import InventoryLog, Order, OrderRequest
from app.services import inventory_service, order_service
from tests.conftest import set_stock, stock_of

MAGGI = "Maggi 70g"


def pid(db, name):
    return next(p.id for p in inventory_service.list_products(db) if p.name == name)


def counts(db):
    db.expire_all()
    return db.query(Order).count(), db.query(InventoryLog).count(), db.query(OrderRequest).count()


def manual_body(db, qty=3):
    return {"customer_id": 1, "items": [{"product_id": pid(db, MAGGI), "quantity": qty}]}


def test_manual_order_retry_returns_same_order_without_double_deduction(client, db):
    set_stock(db, MAGGI, 20)
    headers = {"Idempotency-Key": "retry-key-0001"}
    first = client.post("/api/orders", json=manual_body(db), headers=headers)
    second = client.post("/api/orders", json=manual_body(db), headers=headers)  # e.g. the response was lost
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert counts(db) == (1, 1, 1)
    assert stock_of(db, MAGGI) == 17  # deducted once, not twice


def test_same_key_with_different_details_is_rejected(client, db):
    set_stock(db, MAGGI, 20)
    headers = {"Idempotency-Key": "retry-key-0002"}
    assert client.post("/api/orders", json=manual_body(db, 3), headers=headers).status_code == 201
    clash = client.post("/api/orders", json=manual_body(db, 5), headers=headers)
    assert clash.status_code == 409 and clash.json()["detail"]["code"] == "conflict"
    assert counts(db)[0] == 1 and stock_of(db, MAGGI) == 17


def test_item_order_does_not_change_the_fingerprint(client, db):
    set_stock(db, MAGGI, 20)
    atta = pid(db, "Aashirvaad Atta 5kg")
    a = {"customer_id": 1, "items": [{"product_id": pid(db, MAGGI), "quantity": 2}, {"product_id": atta, "quantity": 1}]}
    b = {"customer_id": 1, "items": [{"product_id": atta, "quantity": 1}, {"product_id": pid(db, MAGGI), "quantity": 2}]}
    headers = {"Idempotency-Key": "retry-key-0003"}
    first = client.post("/api/orders", json=a, headers=headers)
    again = client.post("/api/orders", json=b, headers=headers)
    assert first.json()["id"] == again.json()["id"] and counts(db)[0] == 1


def test_invalid_key_is_rejected_and_key_is_optional(client, db):
    assert client.post("/api/orders", json=manual_body(db), headers={"Idempotency-Key": "short"}).status_code == 422
    assert client.post("/api/orders", json=manual_body(db)).status_code == 201  # no key: behaves as before


def test_failed_order_leaves_no_key_so_the_retry_can_succeed(client, db):
    set_stock(db, MAGGI, 2)
    headers = {"Idempotency-Key": "retry-key-0004"}
    assert client.post("/api/orders", json=manual_body(db, 5), headers=headers).status_code == 409  # not enough stock
    assert counts(db) == (0, 0, 0)  # rolled back: order, stock log AND the key
    set_stock(db, MAGGI, 10)
    assert client.post("/api/orders", json=manual_body(db, 5), headers=headers).status_code == 201


def test_agent_retry_replays_the_confirmation_without_a_second_order(client, db):
    set_stock(db, MAGGI, 20)
    body = {"message": "3 Maggi bhej do", "customer_id": 1}
    headers = {"Idempotency-Key": "agent-key-0001"}
    first = client.post("/api/agent/process", json=body, headers=headers).json()
    second = client.post("/api/agent/process", json=body, headers=headers).json()
    assert first["status"] == second["status"] == "confirmed"
    assert first["order"]["id"] == second["order"]["id"]
    assert [s["name"] for s in second["steps"]] == [s["name"] for s in first["steps"]]  # the stored result
    assert counts(db) == (1, 1, 1) and stock_of(db, MAGGI) == 17


def test_agent_replay_when_the_first_reply_was_lost_before_it_was_stored(client, db):
    """The order committed but the process died before the response was cached."""
    set_stock(db, MAGGI, 20)
    body = {"message": "3 Maggi bhej do", "customer_id": 1}
    headers = {"Idempotency-Key": "agent-key-0002"}
    first = client.post("/api/agent/process", json=body, headers=headers).json()
    db.query(OrderRequest).filter_by(key="agent-key-0002").update({"response": None})
    db.commit()
    replay = client.post("/api/agent/process", json=body, headers=headers).json()
    assert replay["status"] == "confirmed" and replay["order"]["id"] == first["order"]["id"]
    assert "already confirmed" in replay["reply"]
    assert counts(db)[0] == 1 and stock_of(db, MAGGI) == 17


def test_agent_same_key_different_message_is_rejected(client, db):
    headers = {"Idempotency-Key": "agent-key-0003"}
    assert client.post("/api/agent/process", json={"message": "2 Maggi bhej do", "customer_id": 1}, headers=headers).json()["success"]
    other = client.post("/api/agent/process", json={"message": "5 Maggi bhej do", "customer_id": 1}, headers=headers).json()
    assert other["status"] == "error" and "different details" in other["reply"]
    assert counts(db)[0] == 1


def test_rejections_and_clarifications_do_not_consume_the_key(client, db):
    headers = {"Idempotency-Key": "agent-key-0004"}
    res = client.post("/api/agent/process", json={"message": "2 Oreo bhej do", "customer_id": 1}, headers=headers).json()
    assert res["status"] == "rejected" and counts(db) == (0, 0, 0)


def test_concurrent_duplicates_create_exactly_one_order(client, db):
    set_stock(db, MAGGI, 50)
    body = manual_body(db, 4)
    headers = {"Idempotency-Key": "race-key-0001"}

    def call(_):
        return client.post("/api/orders", json=body, headers=headers)

    with ThreadPoolExecutor(6) as pool:
        results = list(pool.map(call, range(6)))
    assert {r.status_code for r in results} <= {201, 409}
    assert len({r.json()["id"] for r in results if r.status_code == 201}) == 1
    assert counts(db) == (1, 1, 1) and stock_of(db, MAGGI) == 46  # one order, one deduction


def test_service_level_duplicate_key_raises_and_rolls_back(db):
    set_stock(db, MAGGI, 20)
    items = [{"product_id": pid(db, MAGGI), "quantity": 2}]
    fp = order_service.payload_fingerprint("order", {"x": 1})
    order_service.create_order(db, 1, items, idempotency_key="svc-key-0001", fingerprint=fp)
    try:
        order_service.create_order(db, 1, items, idempotency_key="svc-key-0001", fingerprint=fp)
        raise AssertionError("expected DuplicateRequestError")
    except order_service.DuplicateRequestError:
        pass
    assert counts(db) == (1, 1, 1) and stock_of(db, MAGGI) == 18
