"""Time helpers. All timestamps are stored as naive UTC; the store's business day is IST."""
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def ist_day_bounds(day_offset: int = 0) -> tuple[datetime, datetime]:
    """(start, end) of an IST calendar day as naive UTC datetimes. offset 0 = today, -1 = yesterday."""
    now_ist = datetime.now(IST)
    start_ist = (now_ist + timedelta(days=day_offset)).replace(hour=0, minute=0, second=0, microsecond=0)
    end_ist = start_ist + timedelta(days=1)
    return (
        start_ist.astimezone(timezone.utc).replace(tzinfo=None),
        end_ist.astimezone(timezone.utc).replace(tzinfo=None),
    )


def money(value: float) -> float:
    return round(float(value) + 1e-9, 2)
