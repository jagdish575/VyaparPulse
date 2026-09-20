from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.ledger_schemas import CustomerIn, ExpenseIn, OpeningIn, PayableIn, PaymentIn, SaleIn
from app.services import ledger_service as ledger

router = APIRouter(prefix="/api/ledger", tags=["ledger"])
DB = Annotated[Session, Depends(get_db)]
Key = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")]


@router.get("/summary")
def summary(db: DB, horizon: int = Query(default=7, ge=1, le=90)):
    return ledger.summary(db, horizon)


@router.post("/opening")
def opening(body: OpeningIn, db: DB, key: Key):
    return ledger.mutate(db, key, "opening", body.model_dump(mode="json"), lambda: ledger.set_opening(db, body))


@router.post("/customers", status_code=201)
def customer(body: CustomerIn, db: DB, key: Key):
    return ledger.mutate(db, key, "customer", body.model_dump(mode="json"), lambda: ledger.create_customer(db, body))


@router.get("/customers/{customer_id}")
def customer_ledger(customer_id: int, db: DB, offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=200)):
    return ledger.customer_ledger(db, customer_id, offset, limit)


@router.get("/invoices")
def invoices(db: DB, customer_id: int | None = None, offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=200)):
    rows = ledger.invoices(db, customer_id)
    return {"total": len(rows), "entries": rows[offset:offset + limit]}


@router.post("/invoices", status_code=201)
def sale(body: SaleIn, db: DB, key: Key):
    return ledger.mutate(db, key, "sale", body.model_dump(mode="json"), lambda: ledger.create_sale(db, body))


@router.post("/invoices/{invoice_id}/payments")
def collect(invoice_id: int, body: PaymentIn, db: DB, key: Key):
    return ledger.mutate(db, key, f"collect:{invoice_id}", body.model_dump(mode="json"), lambda: ledger.collect(db, invoice_id, body))


@router.get("/invoices/{invoice_id}/reminder")
def reminder(invoice_id: int, db: DB):
    return ledger.reminder(db, invoice_id)


@router.get("/payables")
def payables(db: DB, offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=200)):
    rows = ledger.payables(db)
    return {"total": len(rows), "entries": rows[offset:offset + limit]}


@router.post("/payables", status_code=201)
def payable(body: PayableIn, db: DB, key: Key):
    return ledger.mutate(db, key, "payable", body.model_dump(mode="json"), lambda: ledger.create_payable(db, body))


@router.post("/payables/{payable_id}/payments")
def pay_supplier(payable_id: int, body: PaymentIn, db: DB, key: Key):
    return ledger.mutate(db, key, f"pay:{payable_id}", body.model_dump(mode="json"), lambda: ledger.pay_supplier(db, payable_id, body))


@router.post("/expenses", status_code=201)
def expense(body: ExpenseIn, db: DB, key: Key):
    return ledger.mutate(db, key, "expense", body.model_dump(mode="json"), lambda: ledger.expense(db, body))


@router.get("/movements")
def movements(db: DB, offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=200)):
    return ledger.movements(db, offset, limit)
