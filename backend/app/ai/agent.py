"""KirAI agent: customer message -> understanding -> product matching -> live DB lookup -> inventory check
-> price calculation -> atomic order creation + inventory deduction -> confirmation.

The AI (EURI) only *understands* the message. Product identity, price, stock and order ids always come
from the database via the allow-listed tools in app/ai/tools.py. Every step in the returned timeline is
recorded from something that actually ran.
"""
import logging
import time
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.euri_client import EuriClient
from app.ai.parser import ParsedRequest, parse_message
from app.ai.tools import call_tool
from app.config import settings
from app.errors import InsufficientStockError, KiraiError
from app.models import InventoryLog, Product
from app.schemas import (
    AgentRequest,
    AgentResponse,
    AgentStep,
    Clarification,
    ClarificationOption,
    CustomerOut,
    Draft,
    DraftItem,
    InventoryLogOut,
    OrderConfirmation,
    OrderOut,
    ParserInfo,
    ProductCard,
)
from app.services import inventory_service
from app.services.activity_service import log_activity
from app.services.inventory_service import Resolution, choose_from_options, stock_status
from app.services import order_service
from app.services.order_service import ActivityEvent
from app.utils import utcnow

log = logging.getLogger("kirai.agent")

STEP_TITLES = {
    "parse_request": "Understanding request",
    "find_products": "Finding products",
    "check_inventory": "Checking inventory",
    "calculate_total": "Verifying prices",
    "create_order": "Creating order",
    "update_inventory": "Updating inventory",
    "send_confirmation": "Confirming with customer",
}


def inr(value: float) -> str:
    return f"₹{value:,.0f}" if float(value).is_integer() else f"₹{value:,.2f}"


def _join(names: list[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def _card(p: Product) -> ProductCard:
    return ProductCard(
        id=p.id, name=p.name, brand=p.brand, category=p.category, unit=p.unit, price=p.price,
        stock_quantity=p.stock_quantity, stock_status=stock_status(p.stock_quantity, p.low_stock_threshold),
    )


@dataclass
class Line:
    query: str
    quantity: int
    hint: str | None = None
    product_id: int | None = None
    option_ids: list[int] = field(default_factory=list)


class AgentRun:
    """One request through the pipeline. Collects real steps, then builds the response."""

    def __init__(self, db: Session, client: EuriClient, idempotency_key: str | None = None):
        self.db = db
        self.client = client
        self.idem_key = idempotency_key
        self.fingerprint = ""
        self.steps: list[AgentStep] = []
        self.events: list[ActivityEvent] = []
        self.parser: ParserInfo | None = None
        self._tools_used: list[str] = []

    # ---- helpers -------------------------------------------------------------------------------
    def tool(self, name: str, **kwargs):
        self._tools_used.append(name)
        return call_tool(self.db, name, **kwargs)

    def add_step(self, name: str, status: str, message: str, started: float | None = None,
                 ts=None, event: bool = True) -> AgentStep:
        ts = ts or utcnow()
        step = AgentStep(
            name=name, title=STEP_TITLES[name], status=status, message=message, timestamp=ts,
            duration_ms=int((time.perf_counter() - started) * 1000) if started is not None else None,
            tools=self._tools_used,
        )
        self._tools_used = []
        self.steps.append(step)
        if event:
            self.events.append(ActivityEvent(_EVENT_ACTIONS[name], status, message, ts))
        return step

    def skip_remaining(self) -> None:
        done = {s.name for s in self.steps}
        for name in STEP_TITLES:
            if name not in done:
                self.steps.append(AgentStep(name=name, title=STEP_TITLES[name], status="skipped",
                                            message="Not run - request was not completed"))

    def _log(self, action: str, status: str, message: str) -> None:
        try:
            log_activity(self.db, action, status, message)
            self.db.commit()
        except Exception:
            self.db.rollback()
            log.exception("could not write activity log")

    def respond(self, *, intent: str, status: str, reply: str, message: str | None = None, success: bool = False,
                order: OrderConfirmation | None = None, clarification: Clarification | None = None,
                draft: Draft | None = None, products: list[ProductCard] | None = None,
                inventory_updates: list[InventoryLogOut] | None = None) -> AgentResponse:
        return AgentResponse(
            success=success, intent=intent, status=status, steps=self.steps, order=order,
            message=message or reply, reply=reply, clarification=clarification, draft=draft,
            products=products or [], parser=self.parser, inventory_updates=inventory_updates or [],
        )

    # ---- entry ---------------------------------------------------------------------------------
    def execute(self, req: AgentRequest) -> AgentResponse:
        message = req.message.strip()
        customer = self.tool("get_customer", customer_id=req.customer_id or settings.DEMO_CUSTOMER_ID)

        if self.idem_key:  # a retry of an already-processed request returns the earlier result unchanged
            self.fingerprint = order_service.payload_fingerprint("agent", {
                "m": message, "c": customer.id, "a": req.delivery_address,
                "d": req.draft.model_dump() if req.draft else None})
            replay = order_service.check_replay(self.db, self.idem_key, "agent", self.fingerprint)
            if replay:
                return self.replay(replay)

        if not message:
            self.add_step("parse_request", "needs_input", "No request received", time.perf_counter(), event=False)
            return self.respond(intent="place_order", status="needs_input", reply="What would you like to order?")

        # 1) Is this a reply to a pending "which product?" question?
        started = time.perf_counter()
        lines, delivery, address, original = None, None, None, message
        draft = req.draft.model_copy(deep=True) if req.draft else None  # never mutate the caller's object
        if draft:
            pending = next((i for i in draft.items if i.product_id is None and i.option_ids), None)
            if pending:
                options = [p for p in (self.db.get(Product, pid) for pid in pending.option_ids) if p]
                choice = choose_from_options(message, options)
                if choice:
                    pending.product_id, pending.option_ids = choice.id, []
                    lines = [Line(i.query, i.quantity, i.category_hint, i.product_id, list(i.option_ids))
                             for i in draft.items]
                    delivery, address = draft.delivery, draft.delivery_address
                    original = draft.original_request or message
                    self.parser = ParserInfo(provider="local", note="Selection matched to the pending question (no AI call needed)")
                    self.add_step("parse_request", "completed", f"Selection understood: {choice.name}", started)
                    return self.order_flow(customer, lines, delivery, address, original, req)

        # 2) Fresh request: let the AI understand it.
        parsed, self.parser = parse_message(self.client, message)
        return self.dispatch(customer, parsed, message, req, started)

    def dispatch(self, customer, parsed: ParsedRequest, message: str, req: AgentRequest, started: float):
        suffix = " (local parser)" if self.parser and self.parser.provider == "local" else ""
        if parsed.intent == "place_order":
            n = len(parsed.items)
            extra = " · delivery requested" if parsed.delivery else ""
            text = f"Request understood: {n} item{'s' if n != 1 else ''}{extra}{suffix}" if n else f"Order request received, but no products named{suffix}"
            self.add_step("parse_request", "completed", text, started)
            if not parsed.items:
                return self.respond(intent="place_order", status="needs_input", reply="What would you like to order?")
            lines = [Line(i.name.strip(), i.quantity, i.category_hint) for i in parsed.items]
            return self.order_flow(customer, lines, parsed.delivery, parsed.delivery_address, message, req)

        if parsed.intent == "check_stock":
            self.add_step("parse_request", "completed", f"Stock enquiry understood{suffix}", started)
            return self.stock_flow(parsed)

        if parsed.intent == "low_stock":
            self.add_step("parse_request", "completed", f"Low-stock report requested{suffix}", started)
            return self.low_stock_flow()

        self.add_step("parse_request", "completed", f"Message understood - no store action needed{suffix}", started, event=False)
        return self.respond(
            intent="other", status="info", success=True,
            reply="Hi! I'm KirAI, your store operator. Tell me what you'd like to order - for example "
                  "\"2 Maggi aur 1 atta bhej do\" - or ask me about stock, like \"atta khatam ho gaya kya?\"",
        )

    # ---- read-only flows -----------------------------------------------------------------------
    def stock_flow(self, parsed: ParsedRequest) -> AgentResponse:
        if not parsed.items:
            return self.respond(intent="check_stock", status="needs_input", reply="Which product would you like me to check?")
        started = time.perf_counter()
        resolutions: list[Resolution] = self.tool(
            "resolve_products", product_names=[i.name for i in parsed.items],
            category_hints=[i.category_hint for i in parsed.items])
        found = sum(1 for r in resolutions if r.status != "not_found")
        self.add_step("find_products", "completed" if found else "failed",
                      f"{found} of {len(resolutions)} products found in the catalogue", started, event=False)

        started = time.perf_counter()
        cards, lines = [], []
        for r in resolutions:
            if r.status == "not_found":
                lines.append(f"I couldn't find {r.query.title()} in the store inventory.")
                cards.extend(_card(p) for p in r.suggestions)
                continue
            for p in ([r.product] if r.product else r.options):
                inv = self.tool("get_inventory", product_id=p.id)
                cards.append(_card(p))
                lines.append(_stock_line(p, inv["status"]))
        self.add_step("check_inventory", "completed", "Live stock levels read from the database", started, event=False)
        reply = "\n".join(lines)
        self._log("stock_checked", "info", "Stock enquiry: " + "; ".join(l.split(":")[0] for l in lines)[:200])
        return self.respond(intent="check_stock", status="info", success=True, reply=reply,
                            message="Stock checked.", products=_dedupe(cards))

    def low_stock_flow(self) -> AgentResponse:
        started = time.perf_counter()
        products = self.tool("get_low_stock_products")
        self.add_step("check_inventory", "completed", f"{len(products)} products are low or out of stock", started, event=False)
        if not products:
            reply = "Everything is well stocked right now."
        else:
            reply = f"{len(products)} product{'s' if len(products) != 1 else ''} need attention:\n" + "\n".join(
                _stock_line(p, stock_status(p.stock_quantity, p.low_stock_threshold)) for p in products)
        self._log("low_stock_report", "info", f"Low-stock report: {len(products)} products need attention")
        return self.respond(intent="low_stock", status="info", success=True, reply=reply,
                            message="Low stock report ready.", products=[_card(p) for p in products])

    # ---- the main order workflow ---------------------------------------------------------------
    def order_flow(self, customer, lines: list[Line], delivery: bool | None, address: str | None,
                   original: str, req: AgentRequest) -> AgentResponse:
        db = self.db

        # --- validate quantities (never trust the AI's numbers blindly)
        bad = [l for l in lines if l.quantity < 1 or l.quantity > settings.MAX_QTY_PER_ITEM]
        if bad:
            started = time.perf_counter()
            self.add_step("find_products", "failed", "Invalid quantity requested", started, event=False)
            self.skip_remaining()
            names = _join([l.query.title() for l in bad])
            reply = (f"Please tell me a valid quantity for {names} (between 1 and {settings.MAX_QTY_PER_ITEM}). "
                     "I haven't placed the order yet.")
            self._log("request_rejected", "failed", f"Invalid quantity for {names}")
            return self.respond(intent="place_order", status="rejected", reply=reply)

        # --- find products
        started = time.perf_counter()
        to_resolve = [l for l in lines if l.product_id is None]
        resolved = iter(self.tool("resolve_products", product_names=[l.query for l in to_resolve],
                                  category_hints=[l.hint for l in to_resolve]) if to_resolve else [])
        resolutions: list[tuple[Line, Resolution]] = []
        for l in lines:
            if l.product_id is not None:
                p = db.get(Product, l.product_id)
                resolutions.append((l, Resolution(l.query, "matched", product=p) if p and p.is_active
                                    else Resolution(l.query, "not_found")))
            else:
                resolutions.append((l, next(resolved)))

        not_found = [(l, r) for l, r in resolutions if r.status == "not_found"]
        ambiguous = [(l, r) for l, r in resolutions if r.status == "ambiguous"]

        if not_found:
            self.add_step("find_products", "failed", f"Not in catalogue: {_join([r.query.title() for _, r in not_found])}",
                          started, event=True)
            self.skip_remaining()
            return self._reject_not_found(not_found, ambiguous)

        if ambiguous:
            names = _join([r.query for _, r in ambiguous])
            self.add_step("find_products", "needs_input", f"Need clarification for: {names}", started, event=True)
            self.skip_remaining()
            return self._ask_clarification(resolutions, delivery, address, original)

        matched: dict[int, tuple[Product, int]] = {}
        for l, r in resolutions:
            product = r.product
            prev = matched.get(product.id, (product, 0))[1]
            matched[product.id] = (product, prev + l.quantity)
        self.add_step("find_products", "completed",
                      f"{len(matched)} product{'s' if len(matched) != 1 else ''} found: "
                      + ", ".join(p.name for p, _ in matched.values()), started)

        # --- check inventory (live DB)
        started = time.perf_counter()
        problems, short = [], []
        for product, qty in matched.values():
            inv = self.tool("get_inventory", product_id=product.id)
            if inv["stock_quantity"] <= 0:
                problems.append(f"{product.name} is currently out of stock.")
                short.append(f"{product.name} (out of stock)")
            elif inv["stock_quantity"] < qty:
                problems.append(f"Only {inv['stock_quantity']} {product.name} {'is' if inv['stock_quantity'] == 1 else 'are'} currently available.")
                short.append(f"{product.name} (need {qty}, have {inv['stock_quantity']})")
        if problems:
            self.add_step("check_inventory", "failed", "Insufficient stock: " + "; ".join(short), started)
            self.skip_remaining()
            reply = " ".join(problems) + " I haven't placed the order yet."
            self._log_rejection(reply)
            return self.respond(intent="place_order", status="rejected", reply=reply,
                                products=[_card(p) for p, _ in matched.values()])
        self.add_step("check_inventory", "completed", "All products available", started)

        # --- prices from the database
        started = time.perf_counter()
        want_delivery = True if delivery is None else delivery
        drop_address = (address or req.delivery_address or customer.address or "").strip()[:255]
        items = [{"product_id": p.id, "quantity": q} for p, q in matched.values()]
        quote = self.tool("calculate_order", items=items, delivery=want_delivery)
        self.add_step("calculate_total", "completed",
                      f"Verified prices from database: subtotal {inr(quote.subtotal)}"
                      f"{' + delivery ' + inr(quote.delivery_charge) if quote.delivery_charge else ''} = {inr(quote.total)}",
                      started)

        # --- create the order + deduct inventory (one atomic transaction)
        started = time.perf_counter()
        try:
            result = self.tool("create_order", customer_id=customer.id, items=items,
                               delivery_address=drop_address or None, delivery=want_delivery,
                               source="ai_agent", original_request=original, pre_events=list(self.events),
                               idempotency_key=self.idem_key, idempotency_scope="agent",
                               fingerprint=self.fingerprint)
        except order_service.DuplicateRequestError:  # concurrent retry: the other request created the order
            replay = order_service.check_replay(self.db, self.idem_key, "agent", self.fingerprint)
            return self.replay(replay)
        except InsufficientStockError as exc:  # stock changed between the check and the commit
            self.add_step("create_order", "failed", "Stock changed while ordering - nothing was changed", started, event=False)
            self.skip_remaining()
            reply = f"{exc.message} I haven't placed the order yet."
            self._log_rejection(reply)
            return self.respond(intent="place_order", status="rejected", reply=reply)
        except KiraiError as exc:
            self.add_step("create_order", "failed", exc.message, started, event=False)
            self.skip_remaining()
            self._log_rejection(exc.message)
            return self.respond(intent="place_order", status="rejected", reply=f"{exc.message} I haven't placed the order yet.")
        except Exception:
            log.exception("order creation failed")
            self.add_step("create_order", "failed", "Order could not be saved - all changes were rolled back", started, event=False)
            self.skip_remaining()
            self._log_rejection("Order could not be saved; changes rolled back")
            return self.respond(intent="place_order", status="error",
                                reply="Something went wrong while creating the order. Nothing was changed - please try again.")

        order = result.order
        self.add_step("create_order", "completed", f"Order #{order.id} created", started,
                      ts=result.created_event.timestamp, event=False)
        self.add_step("update_inventory", "completed",
                      "Inventory updated: " + ", ".join(f"{c.product.name} {c.stock_before}→{c.stock_after}" for c in result.inventory_changes),
                      ts=result.inventory_event.timestamp, event=False)

        # --- confirmation
        started = time.perf_counter()
        first_name = customer.name.split()[0]
        parts = [f"{l.quantity} × {l.product.name}" for l in result.quote.lines]
        where = f"delivered to {order.delivery_address}" if want_delivery else "ready for pickup at the store"
        reply = (f"Order #{order.id} confirmed, {first_name}! {_join(parts)} will be {where}. "
                 f"Total {inr(order.total)}"
                 f"{' (incl. ' + inr(order.delivery_charge) + ' delivery)' if order.delivery_charge else ''}.")
        self.add_step("send_confirmation", "completed", f"Confirmation ready for {customer.name}", started, event=False)
        try:
            log_activity(db, "confirmation_sent", "completed", f"Confirmation prepared for {customer.name}", order.id)
            db.commit()
        except Exception:
            db.rollback()
            log.exception("could not log confirmation")

        confirmation = OrderConfirmation(
            **OrderOut.model_validate(order).model_dump(),
            customer=CustomerOut.model_validate(order.customer),
            inventory_changes=[InventoryLogOut.model_validate(c) for c in result.inventory_changes],
        )
        return self.respond(intent="place_order", status="confirmed", success=True, order=confirmation,
                            reply=reply, message="Order confirmed successfully.",
                            inventory_updates=confirmation.inventory_changes)

    # ---- outcomes ------------------------------------------------------------------------------
    def replay(self, record) -> AgentResponse:
        """Answer a retry from the stored result. Nothing is created and no stock is touched."""
        if record.response:
            return AgentResponse.model_validate_json(record.response)
        order = order_service.get_order(self.db, record.order_id)  # first attempt committed but its reply was lost
        changes = list(self.db.scalars(select(InventoryLog).where(InventoryLog.order_id == order.id)))
        confirmation = OrderConfirmation(
            **OrderOut.model_validate(order).model_dump(),
            customer=CustomerOut.model_validate(order.customer),
            inventory_changes=[InventoryLogOut.model_validate(c) for c in changes],
        )
        reply = f"Order #{order.id} was already confirmed. Total {inr(order.total)}. Nothing was ordered twice."
        return self.respond(intent="place_order", status="confirmed", success=True, order=confirmation,
                            reply=reply, message="Order confirmed successfully.")

    def _log_rejection(self, text: str) -> None:
        self._log("request_rejected", "failed", text[:300])

    def _reject_not_found(self, not_found, ambiguous) -> AgentResponse:
        names = _join([r.query.title() for _, r in not_found])
        reply = f"I couldn't find {names} in the store inventory."
        suggestions = _dedupe([_card(p) for _, r in not_found for p in r.suggestions])
        if suggestions:
            reply += " You could try: " + ", ".join(f"{c.name} ({inr(c.price)})" for c in suggestions) + "."
        if ambiguous:
            reply += " Also, please tell me exactly which " + _join([r.query for _, r in ambiguous]) + " you want."
        reply += " I haven't placed the order yet."
        self._log_rejection(f"Products not found: {names}")
        return self.respond(intent="place_order", status="rejected", reply=reply, products=suggestions)

    def _ask_clarification(self, resolutions, delivery, address, original) -> AgentResponse:
        first_line, first_res = next((l, r) for l, r in resolutions if r.status == "ambiguous")
        draft_items = []
        for l, r in resolutions:
            draft_items.append(DraftItem(
                query=l.query, quantity=l.quantity, category_hint=l.hint,
                product_id=r.product.id if r.status == "matched" else None,
                option_ids=[p.id for p in r.options] if r.status == "ambiguous" else [],
            ))
        options = [ClarificationOption(
            product_id=p.id, name=p.name, price=p.price, unit=p.unit, stock_quantity=p.stock_quantity,
            stock_status=stock_status(p.stock_quantity, p.low_stock_threshold)) for p in first_res.options]
        question = f"Which {first_line.query} would you like?"
        listing = "\n".join(f"{i}. {o.name} - {inr(o.price)}" for i, o in enumerate(options, 1))
        self._log("clarification_requested", "needs_input", f"Asked customer to choose {first_line.query}: "
                  + ", ".join(o.name for o in options))
        return self.respond(
            intent="place_order", status="needs_clarification",
            reply=f"{question}\n{listing}",
            clarification=Clarification(question=question, item_query=first_line.query, options=options),
            draft=Draft(items=draft_items, delivery=delivery, delivery_address=address, original_request=original),
        )


_EVENT_ACTIONS = {
    "parse_request": "request_parsed",
    "find_products": "products_matched",
    "check_inventory": "inventory_verified",
    "calculate_total": "prices_verified",
    "create_order": "order_created",
    "update_inventory": "inventory_updated",
    "send_confirmation": "confirmation_sent",
}


def _stock_line(p: Product, status: str) -> str:
    if status == "out_of_stock":
        return f"{p.name}: out of stock."
    if status == "low_stock":
        return f"{p.name}: only {p.stock_quantity} left (low stock), {inr(p.price)} per {p.unit}."
    return f"{p.name}: {p.stock_quantity} in stock, {inr(p.price)} per {p.unit}."


def _dedupe(cards: list[ProductCard]) -> list[ProductCard]:
    seen, out = set(), []
    for c in cards:
        if c.id not in seen:
            seen.add(c.id)
            out.append(c)
    return out


def process_message(db: Session, req: AgentRequest, client: EuriClient | None = None,
                    idempotency_key: str | None = None) -> AgentResponse:
    run = AgentRun(db, client or EuriClient(), idempotency_key)
    try:
        result = run.execute(req)
        if idempotency_key and result.order and result.status == "confirmed":
            order_service.store_response(db, idempotency_key, result.model_dump_json())
        return result
    except KiraiError as exc:
        db.rollback()
        return run.respond(intent="unknown", status="error", reply=exc.message)
    except Exception:
        log.exception("agent failed")
        db.rollback()
        return run.respond(intent="unknown", status="error",
                           reply="Something went wrong while processing your request. Nothing was changed - please try again.")
