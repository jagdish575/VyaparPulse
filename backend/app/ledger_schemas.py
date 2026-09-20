from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

# Decimal parsing validates precision before converting to integer paise.
Amount = Annotated[Decimal, Field(ge=0, le=Decimal("999999999.99"), max_digits=11, decimal_places=2)]
PositiveAmount = Annotated[Decimal, Field(gt=0, le=Decimal("999999999.99"), max_digits=11, decimal_places=2)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Method = Literal["cash", "upi", "bank"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OpeningIn(Input):
    amount: Amount


class CustomerIn(Input):
    name: Name
    phone: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\+?[0-9]{7,15}$")]
    address: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] = ""


class SaleIn(Input):
    customer_id: int = Field(gt=0)
    order_id: int | None = Field(default=None, gt=0)
    description: Description
    amount: PositiveAmount
    received: Amount = Decimal("0")
    due_date: date | None = None
    method: Method = "cash"
    kind: Literal["sale", "opening_receivable"] = "sale"

    @model_validator(mode="after")
    def payment_terms(self):
        if self.received > self.amount:
            raise ValueError("Received amount cannot exceed the sale amount.")
        if self.received < self.amount and self.due_date is None:
            raise ValueError("A due date is required for unpaid amounts.")
        if self.kind == "opening_receivable" and (self.received or self.order_id):
            raise ValueError("Opening receivables cannot include a receipt or order.")
        return self


class PaymentIn(Input):
    amount: PositiveAmount
    method: Method = "cash"


class PayableIn(Input):
    supplier: Name
    description: Description
    amount: PositiveAmount
    due_date: date


class ExpenseIn(PaymentIn):
    description: Description
