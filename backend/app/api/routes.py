from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db, init_db
from app.schemas import (
    ActivityOut,
    CustomerDetailOut,
    CustomerOut,
    CustomerSummaryOut,
    InventoryLogOut,
    InventoryOut,
    OrderCreateIn,
    OrderDetailOut,
    OrderOut,
    ProductDetailOut,
    ProductOut,
)
from app.seed import reset_database, seed_database
from app.services import activity_service, customer_service, inventory_service, order_service
from app.utils import utcnow

router = APIRouter(prefix="/api")  # private: mounted behind require_owner in main.py
public_router = APIRouter(prefix="/api")  # public: liveness only
IdemKey = Annotated[str | None, Header(alias="Idempotency-Key", min_length=8, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")]


# ----------------------------------------------------------------------------- health / system

@public_router.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "database": "connected" if db_ok else "unavailable",
        "ai_configured": bool(settings.EURI_API_KEY),
        "time": utcnow().isoformat() + "Z",
    }


@router.get("/settings")
def store_settings(db: Session = Depends(get_db)):
    return {
        "store": {"name": settings.STORE_NAME, "location": settings.STORE_LOCATION,
                  "delivery_charge": settings.DELIVERY_CHARGE, "free_delivery_above": settings.FREE_DELIVERY_ABOVE},
        "ai": {"provider": "EURI", "model": settings.EURI_MODEL, "configured": bool(settings.EURI_API_KEY)},
        "demo_mode": settings.DEMO_MODE,
        "database": {"engine": "SQLite", "products": len(inventory_service.list_products(db, include_inactive=True)),
                     "customers": len(customer_service.list_customers(db)),
                     "orders": order_service.dashboard_stats(db)["total_orders"]},
    }


# ----------------------------------------------------------------------------- products / inventory

@router.get("/products/search", response_model=list[ProductOut])
def search_products(q: str = Query(default="", max_length=100), db: Session = Depends(get_db)):
    return inventory_service.search_products(db, q)


@router.get("/products", response_model=list[ProductOut])
def list_products(
    q: str | None = Query(default=None, max_length=100),
    category: str | None = None,
    status: str | None = Query(default=None, pattern="^(in_stock|low_stock|out_of_stock)$"),
    db: Session = Depends(get_db),
):
    return inventory_service.list_products(db, q, category, status)


@router.get("/products/{product_id}", response_model=ProductDetailOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = inventory_service.get_product(db, product_id)
    data = ProductOut.model_validate(product).model_dump()
    logs = [InventoryLogOut.model_validate(l) for l in inventory_service.product_logs(db, product_id)]
    return ProductDetailOut(**data, logs=logs)


@router.get("/inventory", response_model=InventoryOut)
def inventory(
    q: str | None = Query(default=None, max_length=100),
    category: str | None = None,
    status: str | None = Query(default=None, pattern="^(in_stock|low_stock|out_of_stock)$"),
    db: Session = Depends(get_db),
):
    return InventoryOut(
        summary=inventory_service.inventory_summary(db),
        categories=inventory_service.list_categories(db),
        products=[ProductOut.model_validate(p) for p in inventory_service.list_products(db, q, category, status)],
    )


# ----------------------------------------------------------------------------- orders

@router.get("/orders", response_model=list[OrderOut])
def list_orders(limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db)):
    return order_service.list_orders(db, limit)


@router.post("/orders", response_model=OrderOut, status_code=201)
def create_order(body: OrderCreateIn, db: Session = Depends(get_db), key: IdemKey = None):
    """Send an `Idempotency-Key` header so a retry after a lost response returns the SAME order
    (no second order, no second stock deduction). Reusing a key with different details is rejected (409)."""
    payload = body.model_dump()
    payload["items"] = sorted(payload["items"], key=lambda i: i["product_id"])
    fingerprint = order_service.payload_fingerprint("order", payload)
    if key:
        replay = order_service.check_replay(db, key, "order", fingerprint)
        if replay:
            return order_service.get_order(db, replay.order_id)
    try:
        result = order_service.create_order(
            db, body.customer_id, [i.model_dump() for i in body.items], body.delivery_address, body.delivery,
            source="manual", idempotency_key=key, idempotency_scope="order", fingerprint=fingerprint,
        )
    except order_service.DuplicateRequestError:  # a concurrent retry won the race
        replay = order_service.check_replay(db, key, "order", fingerprint)
        return order_service.get_order(db, replay.order_id)
    return result.order


@router.get("/orders/{order_id}", response_model=OrderDetailOut)
def get_order(order_id: int, db: Session = Depends(get_db)):
    detail = order_service.get_order_detail(db, order_id)
    return OrderDetailOut(
        **OrderOut.model_validate(detail["order"]).model_dump(),
        customer=CustomerOut.model_validate(detail["customer"]),
        activity=[ActivityOut.model_validate(a) for a in detail["activity"]],
        inventory_changes=[InventoryLogOut.model_validate(c) for c in detail["inventory_changes"]],
    )


@router.patch("/orders/{order_id}/status", response_model=OrderOut)
def update_order_status(order_id: int, body: dict, db: Session = Depends(get_db)):
    return order_service.update_order_status(db, order_id, str(body.get("status", "")))


# ----------------------------------------------------------------------------- customers / dashboard / activity

@router.get("/customers", response_model=list[CustomerSummaryOut])
def list_customers(db: Session = Depends(get_db)):
    return customer_service.list_customers(db)


@router.get("/customers/{customer_id}", response_model=CustomerDetailOut)
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    return customer_service.customer_detail(db, customer_id)


@router.get("/dashboard/stats")
def dashboard_stats(db: Session = Depends(get_db)):
    return order_service.dashboard_stats(db)


@router.get("/activity", response_model=list[ActivityOut])
def activity(limit: int = Query(default=60, ge=1, le=300), db: Session = Depends(get_db)):
    return activity_service.list_activity(db, limit)


# ----------------------------------------------------------------------------- demo controls

@router.post("/demo/reset")
def demo_reset():
    counts = reset_database()  # raises ForbiddenError unless DEMO_MODE is on
    return {"success": True, "message": "Demo data reset successfully.", **counts}


@router.post("/seed")
def seed():
    from app.database import SessionLocal
    from app.errors import ForbiddenError

    if not settings.DEMO_MODE:
        raise ForbiddenError("Seeding demo data is disabled. Set DEMO_MODE=true to enable it.")

    init_db()
    with SessionLocal() as db:
        return {"success": True, **seed_database(db)}
