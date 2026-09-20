from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ActivityLog
from app.utils import utcnow


def log_activity(
    db: Session,
    action: str,
    status: str,
    message: str,
    order_id: int | None = None,
    created_at: datetime | None = None,
) -> ActivityLog:
    """Add an activity row to the current transaction (caller commits)."""
    entry = ActivityLog(
        order_id=order_id,
        action=action,
        status=status,
        message=message,
        created_at=created_at or utcnow(),
    )
    db.add(entry)
    return entry


def list_activity(db: Session, limit: int = 60, order_id: int | None = None) -> list[ActivityLog]:
    stmt = select(ActivityLog)
    if order_id is not None:
        stmt = stmt.where(ActivityLog.order_id == order_id)
    stmt = stmt.order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc()).limit(limit)
    return list(db.scalars(stmt))
