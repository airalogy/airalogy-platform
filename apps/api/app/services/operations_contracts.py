"""Amounts are integer CNY fen throughout storage, transport and aggregation."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Money = Annotated[int, Field(strict=True, ge=0, le=999_999_999_999)]
PositiveMoney = Annotated[int, Field(strict=True, gt=0, le=999_999_999_999)]
Role = Literal["lead", "finance", "lead_finance", "viewer"]


def can_manage_contracts(role):
    return role in {"lead", "lead_finance"}


def can_manage_cash(role):
    return role in {"finance", "lead_finance"}


Title = Annotated[str, Field(min_length=1, max_length=255)]
Note = Annotated[str, Field(max_length=4000)]


class Form(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DocumentRef(Form):
    id: UUID
    version: int = Field(ge=1)


class Contract(Form):
    kind: Literal["contract"]
    title: Title
    customer: Title
    number: str = Field(default="", max_length=128)
    state: Literal["draft", "signed"]
    gross: Money
    net: Money | None = None
    agreement_date: date | None = None
    signed_date: date | None = None
    terms: Note = ""
    signed_doc: DocumentRef | None = None
    acceptance_date: date | None = None
    acceptance_doc: DocumentRef | None = None
    work_id: UUID | None = None

    @model_validator(mode="after")
    def signing(self):
        if self.state == "signed" and not self.signed_date:
            raise ValueError("Actual signing date is required")
        if self.net is not None and self.net > self.gross:
            raise ValueError("Net income exceeds gross contract amount")
        return self


class Installment(Form):
    kind: Literal["installment"]
    title: Title
    contract_id: UUID
    amount: PositiveMoney
    condition: Note = ""
    due: date | None = None
    work_id: UUID | None = None


class Cost(Form):
    kind: Literal["cost"]
    title: Title
    day: date
    category: Literal["labor", "subcontract", "material", "cloud", "travel", "other"]
    direct: Money
    payable: Money = 0
    contract_id: UUID | None = None
    days: Annotated[Decimal, Field(gt=0, max_digits=8, decimal_places=2)] | None = None
    rate: Money | None = None

    @model_validator(mode="after")
    def labor(self):
        if self.days is not None or self.rate is not None:
            if self.category != "labor" or self.days is None or self.rate is None:
                raise ValueError("Labor needs both person-days and unit cost")
            if (self.days * self.rate).quantize(
                Decimal(1), rounding=ROUND_HALF_UP
            ) != self.direct:
                raise ValueError(
                    "Direct cost must equal rounded person-days times saved rate"
                )
        return self


class Cash(Form):
    kind: Literal["cash"]
    title: Title
    day: date
    direction: Literal["in", "out"]
    # Omitted on older clients. Preserve the original idempotency digest on retries.
    receipt_purpose: Literal["customer_receipt", "other_income"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    amount: PositiveMoney
    installment_id: UUID | None = None
    cost_id: UUID | None = None
    contract_id: UUID | None = None
    proof_file_id: UUID | None = None

    @model_validator(mode="after")
    def direction_matches(self):
        if self.receipt_purpose and self.direction != "in":
            raise ValueError("Receipt purpose applies only to incoming cash")
        if self.receipt_purpose == "other_income" and (
            self.installment_id or self.contract_id
        ):
            raise ValueError(
                "Only customer receipts can be assigned to a contract or installment"
            )
        if self.direction == "out" and (self.installment_id or self.contract_id):
            raise ValueError("Payment may only be assigned to a cost")
        if self.direction == "in" and self.cost_id:
            raise ValueError(
                "Receipt may only be assigned to a contract or installment"
            )
        return self


class Forecast(Form):
    kind: Literal["forecast"]
    day: date
    remaining: Money | None
    basis: Title


class Closing(Form):
    kind: Literal["closing"]
    day: date
    basis: Title


Content = Annotated[
    Contract | Installment | Cost | Cash | Forecast | Closing,
    Field(discriminator="kind"),
]


class Change(Form):
    request_id: UUID
    entry_id: UUID
    expected_revision: int = Field(ge=0)
    action: Literal["save", "verify", "return", "void"] = "save"
    reason: Note = ""
    data: Content | None = None

    @model_validator(mode="after")
    def appropriate_input(self):
        if (self.action == "save") != (self.data is not None):
            raise ValueError("Supply content only for save")
        if self.expected_revision and self.action != "verify" and not self.reason:
            raise ValueError("A reason is required for a change")
        return self
