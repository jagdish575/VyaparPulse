"""Additive financial tables. Existing orders have no assumed payment status."""
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.utils import utcnow


class LedgerState(Base):
    __tablename__ = "ledger_state"
    __table_args__ = (CheckConstraint("id = 1"), CheckConstraint("opening_paise >= 0"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    opening_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Invoice(Base):
    __tablename__ = "ledger_invoices"
    __table_args__ = (CheckConstraint("total_paise > 0"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), unique=True, nullable=True)
    description: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(30), default="sale")
    total_paise: Mapped[int] = mapped_column(Integer)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Payable(Base):
    __tablename__ = "ledger_payables"
    __table_args__ = (CheckConstraint("total_paise > 0"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(255))
    total_paise: Mapped[int] = mapped_column(Integer)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MoneyMovement(Base):
    __tablename__ = "ledger_movements"
    __table_args__ = (
        CheckConstraint("amount_paise != 0"),
        CheckConstraint("(kind = 'collection' AND amount_paise > 0 AND invoice_id IS NOT NULL AND payable_id IS NULL) OR "
                        "(kind = 'supplier_payment' AND amount_paise < 0 AND payable_id IS NOT NULL AND invoice_id IS NULL) OR "
                        "(kind = 'expense' AND amount_paise < 0 AND invoice_id IS NULL AND payable_id IS NULL)"),
        CheckConstraint("method IN ('cash', 'upi', 'bank')"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("ledger_invoices.id"), nullable=True, index=True)
    payable_id: Mapped[int | None] = mapped_column(ForeignKey("ledger_payables.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(30))
    amount_paise: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(12))
    description: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class LedgerRequest(Base):
    __tablename__ = "ledger_requests"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    response: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
