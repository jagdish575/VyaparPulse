from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils import utcnow


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("stock_quantity >= 0", name="ck_products_stock_non_negative"),
        CheckConstraint("price >= 0", name="ck_products_price_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    brand: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(60), index=True)
    unit: Mapped[str] = mapped_column(String(30))
    price: Mapped[float] = mapped_column(Float)
    stock_quantity: Mapped[int] = mapped_column(Integer, default=0)
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=10)
    description: Mapped[str] = mapped_column(Text, default="")
    # Comma-separated Hinglish / alternate names used by product matching (e.g. "atta, aata, flour").
    aliases: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20), unique=True)
    address: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    orders: Mapped[list["Order"]] = relationship(back_populates="customer")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="confirmed")
    subtotal: Mapped[float] = mapped_column(Float)
    delivery_charge: Mapped[float] = mapped_column(Float, default=0)
    total: Mapped[float] = mapped_column(Float)
    delivery_address: Mapped[str] = mapped_column(String(255))
    # Extra context (not required by the spec, useful for the UI): who created it and the raw request.
    source: Mapped[str] = mapped_column(String(20), default="ai_agent")
    original_request: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    customer: Mapped[Customer] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="OrderItem.id"
    )

    @property
    def customer_name(self) -> str:
        return self.customer.name if self.customer else ""

    @property
    def item_count(self) -> int:
        return sum(i.quantity for i in self.items)


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_order_items_qty_positive"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[float] = mapped_column(Float)
    line_total: Mapped[float] = mapped_column(Float)

    order: Mapped[Order] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()

    @property
    def product_name(self) -> str:
        return self.product.name if self.product else ""

    @property
    def product_unit(self) -> str:
        return self.product.unit if self.product else ""


class InventoryLog(Base):
    __tablename__ = "inventory_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)
    change_type: Mapped[str] = mapped_column(String(30))  # order_deduction | restock | adjustment
    quantity_change: Mapped[int] = mapped_column(Integer)
    stock_before: Mapped[int] = mapped_column(Integer)
    stock_after: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    product: Mapped[Product] = relationship()

    @property
    def product_name(self) -> str:
        return self.product.name if self.product else ""


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20))  # completed | failed | needs_input | info
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class OrderRequest(Base):
    """One row per idempotency key used to create an order (manual or AI). The primary key makes a duplicate
    impossible even under concurrent retries; the row is written in the SAME transaction as the order."""

    __tablename__ = "order_requests"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    scope: Mapped[str] = mapped_column(String(20))  # "order" | "agent"
    fingerprint: Mapped[str] = mapped_column(String(64))
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)  # cached agent response (JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class OwnerSession(Base):
    """Server-side login session. Only the SHA-256 of the cookie token is stored."""

    __tablename__ = "owner_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
