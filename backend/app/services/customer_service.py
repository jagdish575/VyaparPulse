from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import NotFoundError
from app.models import ActivityLog, Customer, Order
from app.services import order_service
from app.utils import money


def get_customer(db: Session, customer_id: int) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise NotFoundError("That customer could not be found.")
    return customer


def _stats(db: Session) -> dict[int, tuple[int, float, object]]:
    rows = db.execute(
        select(Order.customer_id, func.count(Order.id), func.coalesce(func.sum(Order.total), 0), func.max(Order.created_at))
        .where(Order.status != "cancelled")
        .group_by(Order.customer_id)
    ).all()
    return {r[0]: (int(r[1]), money(r[2]), r[3]) for r in rows}


def _summary(customer: Customer, stats: dict) -> dict:
    count, spent, last = stats.get(customer.id, (0, 0.0, None))
    return {
        "id": customer.id,
        "name": customer.name,
        "phone": customer.phone,
        "address": customer.address,
        "created_at": customer.created_at,
        "orders_count": count,
        "total_spent": spent,
        "last_order_at": last,
    }


def list_customers(db: Session) -> list[dict]:
    stats = _stats(db)
    customers = list(db.scalars(select(Customer).order_by(Customer.id)))
    rows = [_summary(c, stats) for c in customers]
    rows.sort(key=lambda r: (-r["total_spent"], r["name"]))
    return rows


def customer_detail(db: Session, customer_id: int) -> dict:
    customer = get_customer(db, customer_id)
    summary = _summary(customer, _stats(db))
    orders = order_service.list_orders(db, limit=50, customer_id=customer_id)
    order_ids = [o.id for o in orders]
    activity = []
    if order_ids:
        activity = list(
            db.scalars(
                select(ActivityLog)
                .where(ActivityLog.order_id.in_(order_ids))
                .order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
                .limit(12)
            )
        )
    count = summary["orders_count"]
    return {
        **summary,
        "average_order_value": money(summary["total_spent"] / count) if count else 0,
        "orders": orders,
        "recent_activity": activity,
    }
