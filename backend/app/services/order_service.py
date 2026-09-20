"""Orders. Creating an order and deducting inventory happen in ONE database transaction."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.errors import InsufficientStockError, KiraiError, NotFoundError, ValidationFailedError
from app.models import ActivityLog, Customer, InventoryLog, Order, OrderItem, Product
from app.services import inventory_service
from app.services.activity_service import log_activity
from app.utils import IST, ist_day_bounds, money, utcnow

ALLOWED_STATUS_UPDATES = {"out_for_delivery", "delivered"}
OPEN_STATUSES = ("confirmed", "out_for_delivery")


@dataclass
class ActivityEvent:
    action: str
    status: str
    message: str
    timestamp: datetime = field(default_factory=utcnow)


@dataclass
class QuoteLine:
    product: Product
    quantity: int
    unit_price: float
    line_total: float


@dataclass
class Quote:
    lines: list[QuoteLine]
    subtotal: float
    delivery_charge: float
    total: float
    delivery: bool

    def to_dict(self) -> dict:
        return {
            "lines": [
                {
                    "product_id": l.product.id,
                    "name": l.product.name,
                    "quantity": l.quantity,
                    "unit_price": l.unit_price,
                    "line_total": l.line_total,
                    "stock_available": l.product.stock_quantity,
                }
                for l in self.lines
            ],
            "subtotal": self.subtotal,
            "delivery_charge": self.delivery_charge,
            "total": self.total,
            "delivery": self.delivery,
        }


@dataclass
class OrderResult:
    order: Order
    quote: Quote
    inventory_changes: list[InventoryLog]
    created_event: ActivityEvent
    inventory_event: ActivityEvent


def delivery_charge_for(subtotal: float, delivery: bool) -> float:
    if not delivery or subtotal >= settings.FREE_DELIVERY_ABOVE:
        return 0.0
    return money(settings.DELIVERY_CHARGE)


def calculate_order(db: Session, items: list[dict], delivery: bool = True) -> Quote:
    """Price an order from the DATABASE (never from the AI). Merges duplicate products."""
    if not items:
        raise ValidationFailedError("An order needs at least one item.")
    merged: dict[int, int] = {}
    for raw in items:
        pid, qty = int(raw["product_id"]), int(raw["quantity"])
        if qty < 1 or qty > settings.MAX_QTY_PER_ITEM:
            raise ValidationFailedError(f"Quantity must be between 1 and {settings.MAX_QTY_PER_ITEM}.")
        merged[pid] = merged.get(pid, 0) + qty

    lines: list[QuoteLine] = []
    for pid, qty in merged.items():
        product = db.get(Product, pid)
        if product is None or not product.is_active:
            raise NotFoundError("One of the products is no longer available in the store.")
        if qty > settings.MAX_QTY_PER_ITEM:
            raise ValidationFailedError(f"Quantity must be between 1 and {settings.MAX_QTY_PER_ITEM}.")
        lines.append(QuoteLine(product, qty, money(product.price), money(product.price * qty)))

    subtotal = money(sum(l.line_total for l in lines))
    charge = delivery_charge_for(subtotal, delivery)
    return Quote(lines, subtotal, charge, money(subtotal + charge), delivery)


def _inventory_summary_text(changes: list[InventoryLog]) -> str:
    return "Inventory updated: " + ", ".join(
        f"{c.product.name} {c.stock_before} → {c.stock_after}" for c in changes
    )


def update_inventory(
    db: Session, order_id: int, *, now: datetime | None = None, commit: bool = True
) -> list[InventoryLog]:
    """Deduct stock for an order. Idempotent: an order is never deducted twice."""
    order = get_order(db, order_id)
    existing = list(
        db.scalars(
            select(InventoryLog).where(
                InventoryLog.order_id == order_id, InventoryLog.change_type == "order_deduction"
            )
        )
    )
    if existing:
        return existing
    try:
        logs = [
            inventory_service.deduct_stock(db, item.product_id, item.quantity, order.id, now)
            for item in order.items
        ]
        if commit:
            db.commit()
        return logs
    except Exception:
        if commit:
            db.rollback()
        raise


def create_order(
    db: Session,
    customer_id: int,
    items: list[dict],
    delivery_address: str | None = None,
    delivery: bool = True,
    *,
    source: str = "ai_agent",
    original_request: str | None = None,
    pre_events: list[ActivityEvent] | None = None,
    created_at: datetime | None = None,
) -> OrderResult:
    """BEGIN → order → items → inventory deduction → inventory logs → activity logs → COMMIT.
    Any failure ROLLBACKs everything: an order is never left partially created."""
    try:
        customer = db.get(Customer, customer_id)
        if customer is None:
            raise NotFoundError("That customer could not be found.")

        quote = calculate_order(db, items, delivery)
        for line in quote.lines:  # friendly pre-check; the atomic UPDATE below is the real guard
            if line.product.stock_quantity < line.quantity:
                raise InsufficientStockError(line.product.name, line.product.stock_quantity, line.quantity)

        now = created_at or utcnow()
        address = (delivery_address or customer.address) if delivery else "Store pickup"
        order = Order(
            customer_id=customer.id,
            status="confirmed",
            subtotal=quote.subtotal,
            delivery_charge=quote.delivery_charge,
            total=quote.total,
            delivery_address=address,
            source=source,
            original_request=original_request,
            created_at=now,
        )
        for line in quote.lines:
            order.items.append(
                OrderItem(
                    product_id=line.product.id,
                    quantity=line.quantity,
                    unit_price=line.unit_price,
                    line_total=line.line_total,
                )
            )
        db.add(order)
        db.flush()  # assigns order.id inside the open transaction

        for ev in pre_events or []:
            log_activity(db, ev.action, ev.status, ev.message, order.id, ev.timestamp)

        created_ev = ActivityEvent(
            "order_created", "completed", f"Order #{order.id} created for {customer.name}",
            created_at or utcnow(),
        )
        log_activity(db, created_ev.action, created_ev.status, created_ev.message, order.id, created_ev.timestamp)

        changes = update_inventory(db, order.id, now=now if created_at else None, commit=False)

        inv_ev = ActivityEvent(
            "inventory_updated", "completed", _inventory_summary_text(changes),
            (created_at + timedelta(seconds=1)) if created_at else utcnow(),
        )
        log_activity(db, inv_ev.action, inv_ev.status, inv_ev.message, order.id, inv_ev.timestamp)

        db.commit()
        return OrderResult(order, quote, changes, created_ev, inv_ev)
    except Exception:
        db.rollback()
        raise


# ----------------------------------------------------------------------------- reads

def get_order(db: Session, order_id: int) -> Order:
    stmt = (
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.items).selectinload(OrderItem.product), selectinload(Order.customer))
    )
    order = db.scalars(stmt).first()
    if order is None:
        raise NotFoundError(f"Order #{order_id} could not be found.")
    return order


def get_order_detail(db: Session, order_id: int) -> dict:
    order = get_order(db, order_id)
    activity = list(
        db.scalars(
            select(ActivityLog)
            .where(ActivityLog.order_id == order_id)
            .order_by(ActivityLog.created_at, ActivityLog.id)
        )
    )
    changes = list(
        db.scalars(
            select(InventoryLog)
            .where(InventoryLog.order_id == order_id)
            .options(selectinload(InventoryLog.product))
            .order_by(InventoryLog.id)
        )
    )
    return {"order": order, "customer": order.customer, "activity": activity, "inventory_changes": changes}


def list_orders(
    db: Session, limit: int = 100, customer_id: int | None = None, status: str | None = None
) -> list[Order]:
    stmt = select(Order).options(
        selectinload(Order.items).selectinload(OrderItem.product), selectinload(Order.customer)
    )
    if customer_id:
        stmt = stmt.where(Order.customer_id == customer_id)
    if status:
        stmt = stmt.where(Order.status == status)
    stmt = stmt.order_by(Order.created_at.desc(), Order.id.desc()).limit(limit)
    return list(db.scalars(stmt))


def update_order_status(db: Session, order_id: int, status: str) -> Order:
    if status not in ALLOWED_STATUS_UPDATES:
        raise ValidationFailedError("Status must be 'out_for_delivery' or 'delivered'.")
    order = get_order(db, order_id)
    if order.status in ("delivered", "cancelled"):
        raise KiraiError(f"Order #{order_id} is already {order.status}.")
    order.status = status
    log_activity(db, "order_status_changed", "completed", f"Order #{order_id} marked {status.replace('_', ' ')}", order_id)
    db.commit()
    return order


# ----------------------------------------------------------------------------- dashboard

def _day_totals(db: Session, start: datetime, end: datetime) -> dict:
    where = (Order.created_at >= start, Order.created_at < end, Order.status != "cancelled")
    orders = db.scalar(select(func.count(Order.id)).where(*where)) or 0
    revenue = db.scalar(select(func.coalesce(func.sum(Order.total), 0)).where(*where)) or 0
    items = (
        db.scalar(
            select(func.coalesce(func.sum(OrderItem.quantity), 0))
            .join(Order, Order.id == OrderItem.order_id)
            .where(*where)
        )
        or 0
    )
    return {"orders": int(orders), "revenue": money(revenue), "items": int(items)}


def _pct_change(current: float, previous: float) -> float | None:
    if previous <= 0:
        return None
    return round((current - previous) / previous * 100, 1)


def dashboard_stats(db: Session) -> dict:
    today = _day_totals(db, *ist_day_bounds(0))
    yesterday = _day_totals(db, *ist_day_bounds(-1))
    inv = inventory_service.inventory_summary(db)

    total_orders = db.scalar(select(func.count(Order.id))) or 0
    total_revenue = db.scalar(select(func.coalesce(func.sum(Order.total), 0)).where(Order.status != "cancelled")) or 0
    pending = db.scalar(select(func.count(Order.id)).where(Order.status.in_(OPEN_STATUSES))) or 0
    ai_orders = db.scalar(select(func.count(Order.id)).where(Order.source == "ai_agent")) or 0

    daily = []
    for offset in range(-6, 1):
        start, end = ist_day_bounds(offset)
        totals = _day_totals(db, start, end)
        label_dt = start.replace(tzinfo=None) + timedelta(hours=5, minutes=30)
        daily.append({"date": label_dt.strftime("%a"), "orders": totals["orders"], "revenue": totals["revenue"]})

    top = db.execute(
        select(Product.id, Product.name, func.sum(OrderItem.quantity).label("qty"))
        .join(OrderItem, OrderItem.product_id == Product.id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.status != "cancelled")
        .group_by(Product.id)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(5)
    ).all()

    return {
        "today": today,
        "yesterday": yesterday,
        "orders_today": today["orders"],
        "revenue_today": today["revenue"],
        "items_sold_today": today["items"],
        "orders_trend_pct": _pct_change(today["orders"], yesterday["orders"]),
        "revenue_trend_pct": _pct_change(today["revenue"], yesterday["revenue"]),
        "items_trend_pct": _pct_change(today["items"], yesterday["items"]),
        "low_stock_count": inv["low_stock"],
        "out_of_stock_count": inv["out_of_stock"],
        "total_products": inv["total_products"],
        "stock_value": inv["stock_value"],
        "total_orders": int(total_orders),
        "total_revenue": money(total_revenue),
        "pending_orders": int(pending),
        "ai_handled_orders": int(ai_orders),
        "daily": daily,
        "top_products": [{"product_id": r[0], "name": r[1], "quantity": int(r[2])} for r in top],
    }
