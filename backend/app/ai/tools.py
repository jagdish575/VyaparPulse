"""Tool registry: the ONLY operations the AI pipeline may run.

The model never touches SQL. It only produces a structured request; the backend agent then calls these
allow-listed, validated functions, which in turn use the service layer (the database is the source of truth).
"""
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.services import customer_service, inventory_service, order_service


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict
    fn: Callable[..., Any]


def _resolve_products(db: Session, product_names: list[str], category_hints: list[str | None] | None = None):
    hints = category_hints or [None] * len(product_names)
    return [inventory_service.resolve_product(db, n, h) for n, h in zip(product_names, hints)]


_TOOL_LIST = [
    Tool("search_products", "Search the store catalogue by text.", {"query": "string"},
         lambda db, query: inventory_service.search_products(db, query)),
    Tool("get_product", "Get one product (price, unit, stock).", {"product_id": "integer"},
         lambda db, product_id: inventory_service.get_product(db, product_id)),
    Tool("get_inventory", "Get live stock level and status for a product.", {"product_id": "integer"},
         lambda db, product_id: inventory_service.get_inventory(db, product_id)),
    Tool("resolve_products", "Map customer product phrases to real catalogue products.",
         {"product_names": "string[]"}, _resolve_products),
    Tool("get_low_stock_products", "List products that are low or out of stock.", {},
         lambda db: inventory_service.low_stock_products(db)),
    Tool("calculate_order", "Price an order from database prices.", {"items": "[{product_id, quantity}]"},
         lambda db, items, delivery=True: order_service.calculate_order(db, items, delivery)),
    Tool("create_order", "Atomically create an order and deduct inventory.",
         {"customer_id": "integer", "items": "[{product_id, quantity}]", "delivery_address": "string"},
         lambda db, customer_id, items, delivery_address=None, **kw: order_service.create_order(
             db, customer_id, items, delivery_address, **kw)),
    Tool("update_inventory", "Apply the stock deduction for an order (idempotent).", {"order_id": "integer"},
         lambda db, order_id, **kw: order_service.update_inventory(db, order_id, **kw)),
    Tool("get_order", "Fetch an order with its items.", {"order_id": "integer"},
         lambda db, order_id: order_service.get_order(db, order_id)),
    Tool("get_customer", "Fetch a customer.", {"customer_id": "integer"},
         lambda db, customer_id: customer_service.get_customer(db, customer_id)),
]

TOOLS: dict[str, Tool] = {t.name: t for t in _TOOL_LIST}


def call_tool(db: Session, name: str, **kwargs: Any) -> Any:
    tool = TOOLS.get(name)
    if tool is None:
        raise ValueError(f"Tool '{name}' is not allowed")
    return tool.fn(db, **kwargs)


def describe_tools() -> list[dict]:
    """Tool catalogue in the shape EuriClient.tool_call() expects."""
    return [{"name": t.name, "description": t.description, "parameters": t.parameters} for t in _TOOL_LIST]
