from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, computed_field, field_validator

from app.config import settings


def _iso_utc(dt: datetime) -> str:
    """Timestamps are stored as naive UTC; always send them with an explicit Z."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


UTCDateTime = Annotated[datetime, PlainSerializer(_iso_utc, return_type=str)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ----------------------------------------------------------------------------- products / inventory

class ProductOut(ORM):
    id: int
    name: str
    brand: str
    category: str
    unit: str
    price: float
    stock_quantity: int
    low_stock_threshold: int
    description: str
    aliases: str = ""
    is_active: bool
    created_at: UTCDateTime
    updated_at: UTCDateTime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def stock_status(self) -> str:
        from app.services.inventory_service import stock_status

        return stock_status(self.stock_quantity, self.low_stock_threshold)


class InventoryLogOut(ORM):
    id: int
    product_id: int
    product_name: str
    order_id: int | None
    change_type: str
    quantity_change: int
    stock_before: int
    stock_after: int
    created_at: UTCDateTime


class ProductDetailOut(ProductOut):
    logs: list[InventoryLogOut] = []


class InventoryOut(BaseModel):
    summary: dict[str, Any]
    categories: list[str]
    products: list[ProductOut]


# ----------------------------------------------------------------------------- customers / orders

class CustomerOut(ORM):
    id: int
    name: str
    phone: str
    address: str
    created_at: UTCDateTime


class OrderItemOut(ORM):
    id: int
    product_id: int
    product_name: str
    product_unit: str
    quantity: int
    unit_price: float
    line_total: float


class ActivityOut(ORM):
    id: int
    order_id: int | None
    action: str
    status: str
    message: str
    created_at: UTCDateTime


class OrderOut(ORM):
    id: int
    customer_id: int
    customer_name: str
    status: str
    subtotal: float
    delivery_charge: float
    total: float
    delivery_address: str
    source: str
    original_request: str | None = None
    item_count: int
    items: list[OrderItemOut]
    created_at: UTCDateTime


class OrderDetailOut(OrderOut):
    customer: CustomerOut
    activity: list[ActivityOut] = []
    inventory_changes: list[InventoryLogOut] = []


class CustomerSummaryOut(CustomerOut):
    orders_count: int = 0
    total_spent: float = 0
    last_order_at: UTCDateTime | None = None


class CustomerDetailOut(CustomerSummaryOut):
    average_order_value: float = 0
    orders: list[OrderOut] = []
    recent_activity: list[ActivityOut] = []


# ----------------------------------------------------------------------------- manual order API

class OrderLineIn(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=settings.MAX_QTY_PER_ITEM)


class OrderCreateIn(BaseModel):
    customer_id: int = Field(gt=0)
    items: list[OrderLineIn] = Field(min_length=1, max_length=25)
    delivery_address: str | None = Field(default=None, max_length=255)
    delivery: bool = True

    @field_validator("delivery_address")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return v.strip() or None if v else None


# ----------------------------------------------------------------------------- agent API

class DraftItem(BaseModel):
    query: str = Field(max_length=120)
    quantity: int = Field(ge=1, le=1000)
    category_hint: str | None = Field(default=None, max_length=60)
    product_id: int | None = None
    option_ids: list[int] = []


class Draft(BaseModel):
    """Conversation state for a request that is waiting for the customer to pick a product."""

    items: list[DraftItem] = Field(default_factory=list, max_length=25)
    delivery: bool | None = None
    delivery_address: str | None = Field(default=None, max_length=255)
    original_request: str | None = Field(default=None, max_length=600)


class AgentRequest(BaseModel):
    message: str = Field(default="", max_length=600)
    customer_id: int | None = Field(default=None, gt=0)
    delivery_address: str | None = Field(default=None, max_length=255)
    draft: Draft | None = None


class AgentStep(BaseModel):
    name: str
    title: str
    status: Literal["completed", "failed", "needs_input", "skipped"]
    message: str
    timestamp: UTCDateTime | None = None
    duration_ms: int | None = None
    tools: list[str] = []


class ClarificationOption(BaseModel):
    product_id: int
    name: str
    price: float
    unit: str
    stock_quantity: int
    stock_status: str


class Clarification(BaseModel):
    question: str
    item_query: str
    options: list[ClarificationOption]


class ProductCard(BaseModel):
    id: int
    name: str
    brand: str
    category: str
    unit: str
    price: float
    stock_quantity: int
    stock_status: str


class OrderConfirmation(OrderOut):
    """Order payload returned from the agent: id/subtotal/delivery_charge/total plus full detail."""

    customer: CustomerOut
    inventory_changes: list[InventoryLogOut] = []


class ParserInfo(BaseModel):
    provider: Literal["euri", "local"]
    model: str | None = None
    note: str | None = None


class AgentResponse(BaseModel):
    success: bool
    intent: str
    status: Literal["confirmed", "needs_clarification", "needs_input", "rejected", "info", "error"]
    steps: list[AgentStep]
    order: OrderConfirmation | None = None
    message: str
    reply: str
    clarification: Clarification | None = None
    draft: Draft | None = None
    products: list[ProductCard] = []
    parser: ParserInfo | None = None
    inventory_updates: list[InventoryLogOut] = []
