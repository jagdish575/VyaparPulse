"""Exact financial records. Every mutation is serialized and committed with its retry result."""
import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import KiraiError, NotFoundError, ValidationFailedError
from app.ledger_models import Invoice, LedgerRequest, LedgerState, MoneyMovement, Payable
from app.models import Customer, Order
from app.utils import IST, utcnow


class Conflict(KiraiError):
    status_code = 409
    code = "ledger_conflict"


def paise(amount: Decimal) -> int:
    return int(amount * 100)


def today():
    return datetime.now(IST).date()


def stamp(dt):
    return dt.isoformat() + "Z" if dt else None


def require(db, model, identifier):
    record = db.get(model, identifier)
    if record is None:
        raise NotFoundError("That record could not be found.")
    return record


def mutate(db: Session, key: str, operation: str, payload: dict, action):
    fingerprint = hashlib.sha256(json.dumps([operation, payload], sort_keys=True).encode()).hexdigest()
    try:
        # This write locks the singleton until commit. SQLite serializes writers; row
        # databases lock this row. Read balances ONLY after obtaining this lock.
        db.execute(update(LedgerState).where(LedgerState.id == 1).values(revision=LedgerState.revision + 1))
        previous = db.get(LedgerRequest, key)
        if previous:
            if previous.fingerprint != fingerprint:
                raise Conflict("This request key was already used for different details. Start a new entry.")
            response = json.loads(previous.response)
            db.rollback()
            return response
        result = action()
        db.add(LedgerRequest(key=key, fingerprint=fingerprint, response=json.dumps(result)))
        db.commit()
        return result
    except IntegrityError as exc:
        db.rollback()
        raise Conflict("This customer or order has already been recorded. Refresh and check the existing record.") from exc
    except Exception:
        db.rollback()
        raise


def require_opening(db):
    state = require(db, LedgerState, 1)
    if state.opening_paise is None:
        raise Conflict("Set opening funds before recording financial entries.")
    return state


def set_opening(db, body):
    state = require(db, LedgerState, 1)
    if state.opening_paise is not None:
        raise Conflict("Opening funds have already been set.")
    state.opening_paise = paise(body.amount)
    state.started_at = utcnow()
    db.flush()
    return {"opening_paise": state.opening_paise, "started_at": stamp(state.started_at)}


def create_customer(db, body):
    customer = Customer(**body.model_dump())
    db.add(customer)
    db.flush()
    return {"id": customer.id, "name": customer.name, "phone": customer.phone}


def received(db, invoice_id):
    return int(db.scalar(select(func.coalesce(func.sum(MoneyMovement.amount_paise), 0))
                         .where(MoneyMovement.invoice_id == invoice_id)) or 0)


def invoice_data(db, invoice, paid=None):
    paid = received(db, invoice.id) if paid is None else paid
    balance = invoice.total_paise - paid
    return {"id": invoice.id, "customer_id": invoice.customer_id,
            "customer_name": require(db, Customer, invoice.customer_id).name,
            "order_id": invoice.order_id, "description": invoice.description, "kind": invoice.kind,
            "total_paise": invoice.total_paise, "received_paise": paid, "outstanding_paise": balance,
            "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
            "status": "paid" if balance == 0 else "overdue" if invoice.due_date and invoice.due_date < today() else "upcoming",
            "created_at": stamp(invoice.created_at)}


def add_movement(db, amount, kind, method, description, invoice_id=None, payable_id=None):
    movement = MoneyMovement(amount_paise=amount, kind=kind, method=method, description=description,
                             invoice_id=invoice_id, payable_id=payable_id)
    db.add(movement)
    db.flush()
    return movement


def create_sale(db, body):
    require_opening(db)
    require(db, Customer, body.customer_id)
    total = paise(body.amount)
    if body.order_id:
        order = require(db, Order, body.order_id)
        if order.customer_id != body.customer_id or order.status == "cancelled":
            raise ValidationFailedError("Select an active order belonging to this customer.")
        # Legacy order totals have float storage. Convert exactly once at the ledger
        # boundary, using decimal text and explicit rounding, never a float sum.
        order_paise = int((Decimal(str(order.total)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        if total != order_paise:
            raise ValidationFailedError("The invoice amount must match the order total.")
    invoice = Invoice(customer_id=body.customer_id, order_id=body.order_id, description=body.description,
                      total_paise=total, due_date=body.due_date, kind=body.kind)
    db.add(invoice)
    db.flush()
    if body.received:
        add_movement(db, paise(body.received), "collection", body.method, f"Receipt for invoice #{invoice.id}", invoice_id=invoice.id)
    return invoice_data(db, invoice)


def collect(db, invoice_id, body):
    require_opening(db)
    invoice = require(db, Invoice, invoice_id)
    amount = paise(body.amount)
    if amount > invoice.total_paise - received(db, invoice_id):
        raise Conflict("Payment exceeds the remaining invoice balance. Refresh the ledger.")
    add_movement(db, amount, "collection", body.method, f"Receipt for invoice #{invoice_id}", invoice_id=invoice_id)
    return invoice_data(db, invoice)


def payable_data(db, payable, paid=None):
    if paid is None:
        paid = -int(db.scalar(select(func.coalesce(func.sum(MoneyMovement.amount_paise), 0))
                              .where(MoneyMovement.payable_id == payable.id)) or 0)
    balance = payable.total_paise - paid
    return {"id": payable.id, "supplier": payable.supplier, "description": payable.description,
            "total_paise": payable.total_paise, "paid_paise": paid, "outstanding_paise": balance,
            "due_date": payable.due_date.isoformat(),
            "status": "paid" if balance == 0 else "overdue" if payable.due_date < today() else "upcoming"}


def create_payable(db, body):
    require_opening(db)
    payable = Payable(supplier=body.supplier, description=body.description, total_paise=paise(body.amount), due_date=body.due_date)
    db.add(payable)
    db.flush()
    return payable_data(db, payable)


def pay_supplier(db, payable_id, body):
    require_opening(db)
    payable = require(db, Payable, payable_id)
    if paise(body.amount) > payable_data(db, payable)["outstanding_paise"]:
        raise Conflict("Payment exceeds the remaining supplier balance.")
    add_movement(db, -paise(body.amount), "supplier_payment", body.method,
                 f"Payment to {payable.supplier}", payable_id=payable.id)
    return payable_data(db, payable)


def expense(db, body):
    require_opening(db)
    movement = add_movement(db, -paise(body.amount), "expense", body.method, body.description)
    return {"id": movement.id, "amount_paise": movement.amount_paise}


def invoices(db, customer_id=None):
    query = select(Invoice).order_by(Invoice.created_at.desc(), Invoice.id.desc())
    if customer_id is not None:
        query = query.where(Invoice.customer_id == customer_id)
    totals = dict(db.execute(select(MoneyMovement.invoice_id, func.sum(MoneyMovement.amount_paise))
                             .where(MoneyMovement.invoice_id.is_not(None)).group_by(MoneyMovement.invoice_id)).all())
    return [invoice_data(db, invoice, totals.get(invoice.id, 0)) for invoice in db.scalars(query)]


def payables(db):
    totals = dict(db.execute(select(MoneyMovement.payable_id, func.sum(MoneyMovement.amount_paise))
                             .where(MoneyMovement.payable_id.is_not(None)).group_by(MoneyMovement.payable_id)).all())
    return [payable_data(db, p, -totals.get(p.id, 0)) for p in db.scalars(select(Payable).order_by(Payable.due_date, Payable.id))]


def summary(db, horizon=7):
    state = require(db, LedgerState, 1)
    inv = invoices(db)
    bills = payables(db)
    now = today()
    # Half-open date window: today and the next horizon-1 business dates.
    end = now + timedelta(days=horizon)
    due = lambda row: row["due_date"] and row["due_date"] < end.isoformat()
    overdue = [i for i in inv if i["status"] == "overdue"]
    movements = int(db.scalar(select(func.coalesce(func.sum(MoneyMovement.amount_paise), 0))) or 0)
    available = None if state.opening_paise is None else state.opening_paise + movements
    obligations = sum(p["outstanding_paise"] for p in bills if due(p))
    shortfall = None if available is None else max(0, obligations - available)
    priorities = sorted(overdue, key=lambda i: (-i["outstanding_paise"], i["due_date"], i["id"]))[:5]
    unrecorded = db.scalar(select(func.count(Order.id)).where(Order.status != "cancelled",
                          ~Order.id.in_(select(Invoice.order_id).where(Invoice.order_id.is_not(None))))) or 0
    return {"configured": state.opening_paise is not None, "started_at": stamp(state.started_at),
            "opening_paise": state.opening_paise, "net_movements_paise": movements, "available_paise": available,
            "sales_paise": sum(i["total_paise"] for i in inv if i["kind"] == "sale"),
            "receivables_paise": sum(i["outstanding_paise"] for i in inv),
            "overdue_paise": sum(i["outstanding_paise"] for i in overdue),
            "upcoming_paise": sum(i["outstanding_paise"] for i in inv if i["due_date"] and now.isoformat() <= i["due_date"] < end.isoformat()),
            "supplier_due_paise": obligations, "shortfall_paise": shortfall,
            "horizon_days": horizon, "through_date": (end - timedelta(days=1)).isoformat(),
            "priorities": priorities, "unrecorded_orders": unrecorded}


def reminder(db, invoice_id):
    invoice = require(db, Invoice, invoice_id)
    data = invoice_data(db, invoice)
    if data["outstanding_paise"] == 0:
        raise Conflict("This invoice is settled; no payment reminder is needed.")
    amount = Decimal(data["outstanding_paise"]) / 100
    return {"invoice_id": invoice.id, "outstanding_paise": data["outstanding_paise"],
            "text": f"Hello {data['customer_name']}, Rs {amount:,.2f} remains unpaid on invoice #{invoice.id}, "
                    f"due {data['due_date']}. Please arrange payment. Thank you."}


def customer_ledger(db, customer_id, offset=0, limit=50):
    customer = require(db, Customer, customer_id)
    entries = []
    for invoice in db.scalars(select(Invoice).where(Invoice.customer_id == customer_id)):
        entries.append({"id": f"invoice-{invoice.id}", "invoice_id": invoice.id, "kind": invoice.kind,
                        "description": invoice.description, "amount_paise": invoice.total_paise,
                        "created_at": stamp(invoice.created_at), "sequence": (invoice.created_at, 0, invoice.id)})
    for m in db.scalars(select(MoneyMovement).join(Invoice, Invoice.id == MoneyMovement.invoice_id)
                        .where(Invoice.customer_id == customer_id)):
        entries.append({"id": f"payment-{m.id}", "invoice_id": m.invoice_id, "kind": m.kind,
                        "description": m.description, "amount_paise": -m.amount_paise,
                        "created_at": stamp(m.created_at), "sequence": (m.created_at, 1, m.id)})
    entries.sort(key=lambda e: e["sequence"])
    balance = 0
    for entry in entries:
        balance += entry["amount_paise"]
        entry["balance_paise"] = balance
        del entry["sequence"]
    return {"customer_id": customer_id, "customer_name": customer.name, "balance_paise": balance,
            "total": len(entries), "offset": offset, "entries": entries[offset:offset + limit]}


def movements(db, offset=0, limit=50):
    rows = db.scalars(select(MoneyMovement).order_by(MoneyMovement.id.desc()).offset(offset).limit(limit))
    return {"total": db.scalar(select(func.count(MoneyMovement.id))),
            "entries": [{"id": m.id, "kind": m.kind, "description": m.description, "method": m.method,
                         "amount_paise": m.amount_paise, "created_at": stamp(m.created_at)} for m in rows]}
