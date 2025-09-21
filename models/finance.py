"""Pydantic models representing the core financial planning inputs."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Iterable, List, Literal, Sequence

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

MonthIndex = Literal[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
MONTH_SEQUENCE: Sequence[MonthIndex] = tuple(range(1, 13))  # type: ignore[arg-type]


class MonthlySeries(BaseModel):
    """A 12-month series of Decimal amounts."""

    amounts: List[Decimal] = Field(default_factory=list)

    @field_validator("amounts", mode="before")
    @classmethod
    def _coerce_list(cls, value: Iterable[Decimal] | Dict[int, Decimal]) -> List[Decimal]:
        if isinstance(value, dict):
            ordered = [value.get(month, Decimal("0")) for month in MONTH_SEQUENCE]
            return [Decimal(str(v)) for v in ordered]
        if not isinstance(value, Iterable):
            raise TypeError("月次データは12項目のリストで入力してください。")
        coerced = [Decimal(str(v)) for v in value]
        return coerced

    @model_validator(mode="after")
    def _ensure_twelve(self) -> "MonthlySeries":
        if len(self.amounts) != 12:
            raise ValueError("月次データは必ず12ヶ月分を入力してください。")
        return self

    def total(self) -> Decimal:
        return sum(self.amounts, start=Decimal("0"))

    def by_month(self) -> Dict[MonthIndex, Decimal]:
        return {month: self.amounts[i] for i, month in enumerate(MONTH_SEQUENCE)}


class SalesItem(BaseModel):
    """Monthly sales for a specific product sold through a channel."""

    channel: str
    product: str
    monthly: MonthlySeries = Field(default_factory=MonthlySeries)

    @property
    def annual_total(self) -> Decimal:
        return self.monthly.total()


class SalesPlan(BaseModel):
    """Sales broken down by channel, product and month."""

    items: List[SalesItem] = Field(default_factory=list)

    def total_by_month(self) -> Dict[MonthIndex, Decimal]:
        totals = {month: Decimal("0") for month in MONTH_SEQUENCE}
        for item in self.items:
            for month, value in item.monthly.by_month().items():
                totals[month] += value
        return totals

    def annual_total(self) -> Decimal:
        return sum((item.annual_total for item in self.items), start=Decimal("0"))

    def channels(self) -> List[str]:
        return sorted({item.channel for item in self.items})

    def products(self) -> List[str]:
        return sorted({item.product for item in self.items})


class CostPlan(BaseModel):
    """Cost configuration split into variable ratios and fixed amounts."""

    variable_ratios: Dict[str, Decimal] = Field(default_factory=dict)
    fixed_costs: Dict[str, Decimal] = Field(default_factory=dict)
    gross_linked_ratios: Dict[str, Decimal] = Field(default_factory=dict)
    non_operating_income: Dict[str, Decimal] = Field(default_factory=dict)
    non_operating_expenses: Dict[str, Decimal] = Field(default_factory=dict)

    @field_validator("variable_ratios", "gross_linked_ratios", mode="before")
    @classmethod
    def _coerce_ratio_dict(cls, value: Dict[str, Decimal] | None) -> Dict[str, Decimal]:
        if value is None:
            return {}
        return {str(k): Decimal(str(v)) for k, v in value.items()}

    @field_validator(
        "fixed_costs", "non_operating_income", "non_operating_expenses", mode="before"
    )
    @classmethod
    def _coerce_amount_dict(cls, value: Dict[str, Decimal] | None) -> Dict[str, Decimal]:
        if value is None:
            return {}
        return {str(k): Decimal(str(v)) for k, v in value.items()}

    @model_validator(mode="after")
    def _check_ranges(self) -> "CostPlan":
        for label, ratios in (
            ("variable_ratios", self.variable_ratios),
            ("gross_linked_ratios", self.gross_linked_ratios),
        ):
            for code, ratio in ratios.items():
                if ratio < Decimal("0") or ratio > Decimal("1"):
                    raise ValueError(f"{label} の '{code}' は0〜1の範囲に収めてください。")
        for label, amounts in (
            ("fixed_costs", self.fixed_costs),
            ("non_operating_income", self.non_operating_income),
            ("non_operating_expenses", self.non_operating_expenses),
        ):
            for code, amount in amounts.items():
                if amount < Decimal("0"):
                    raise ValueError(f"{label} の '{code}' は0以上の金額を入力してください。")
        return self


class CapexItem(BaseModel):
    """Single capital expenditure entry."""

    name: str
    amount: Decimal
    start_month: MonthIndex
    useful_life_years: int = Field(ge=1, le=20)

    @field_validator("amount", mode="before")
    @classmethod
    def _coerce_amount(cls, value: Decimal) -> Decimal:
        return Decimal(str(value))

    @model_validator(mode="after")
    def _ensure_positive_amount(self) -> "CapexItem":
        if self.amount <= 0:
            raise ValueError("投資金額は正の値を入力してください。")
        return self

    def annual_depreciation(self) -> Decimal:
        life_months = Decimal(self.useful_life_years * 12)
        return self.amount / (life_months / Decimal("12"))


class CapexPlan(BaseModel):
    items: List[CapexItem] = Field(default_factory=list)

    def annual_depreciation(self) -> Decimal:
        return sum((item.annual_depreciation() for item in self.items), start=Decimal("0"))

    def total_investment(self) -> Decimal:
        return sum((item.amount for item in self.items), start=Decimal("0"))


class LoanItem(BaseModel):
    """Definition of a single borrowing schedule."""

    name: str
    principal: Decimal
    interest_rate: Decimal = Field(ge=Decimal("0"), le=Decimal("0.2"))
    term_months: int = Field(ge=1, le=600)
    start_month: MonthIndex
    repayment_type: Literal["equal_principal", "interest_only"] = "equal_principal"

    @field_validator("principal", mode="before")
    @classmethod
    def _coerce_principal(cls, value: Decimal) -> Decimal:
        return Decimal(str(value))

    @field_validator("interest_rate", mode="before")
    @classmethod
    def _coerce_rate(cls, value: Decimal) -> Decimal:
        rate = Decimal(str(value))
        if rate < Decimal("0") or rate > Decimal("0.2"):
            raise ValueError("金利は0%〜20%の範囲で入力してください。")
        return rate

    @model_validator(mode="after")
    def _ensure_positive_principal(self) -> "LoanItem":
        if self.principal <= 0:
            raise ValueError("借入元本は正の値を入力してください。")
        return self

    def annual_interest(self) -> Decimal:
        return self.principal * self.interest_rate


class LoanSchedule(BaseModel):
    loans: List[LoanItem] = Field(default_factory=list)

    def annual_interest(self) -> Decimal:
        return sum((loan.annual_interest() for loan in self.loans), start=Decimal("0"))

    def outstanding_principal(self) -> Decimal:
        return sum((loan.principal for loan in self.loans), start=Decimal("0"))


class TaxPolicy(BaseModel):
    corporate_tax_rate: Decimal = Field(default=Decimal("0.30"))
    consumption_tax_rate: Decimal = Field(default=Decimal("0.10"))
    dividend_payout_ratio: Decimal = Field(default=Decimal("0.0"))

    @field_validator(
        "corporate_tax_rate", "consumption_tax_rate", "dividend_payout_ratio", mode="before"
    )
    @classmethod
    def _coerce_rate(cls, value: Decimal) -> Decimal:
        rate = Decimal(str(value))
        return rate

    @model_validator(mode="after")
    def _validate_ranges(self) -> "TaxPolicy":
        if not Decimal("0") <= self.corporate_tax_rate <= Decimal("0.55"):
            raise ValueError("法人税率は0%〜55%の範囲で設定してください。")
        if not Decimal("0") <= self.consumption_tax_rate <= Decimal("0.20"):
            raise ValueError("消費税率は0%〜20%の範囲で設定してください。")
        if not Decimal("0") <= self.dividend_payout_ratio <= Decimal("1"):
            raise ValueError("配当性向は0%〜100%の範囲で設定してください。")
        return self

    def effective_tax(self, ordinary_income: Decimal) -> Decimal:
        if ordinary_income <= 0:
            return Decimal("0")
        return ordinary_income * self.corporate_tax_rate

    def projected_dividend(self, net_income: Decimal) -> Decimal:
        if net_income <= 0:
            return Decimal("0")
        return net_income * self.dividend_payout_ratio


@dataclass(frozen=True)
class FinanceBundle:
    """Convenience container to pass around typed plan inputs."""

    sales: SalesPlan
    costs: CostPlan
    capex: CapexPlan
    loans: LoanSchedule
    tax: TaxPolicy

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "FinanceBundle":
        try:
            sales = SalesPlan(**data.get("sales", {}))
            costs = CostPlan(**data.get("costs", {}))
            capex = CapexPlan(**data.get("capex", {}))
            loans = LoanSchedule(**data.get("loans", {}))
            tax = TaxPolicy(**data.get("tax", {}))
        except ValidationError as exc:  # pragma: no cover - defensive
            raise ValueError("無効な財務データが含まれています。") from exc
        return cls(sales=sales, costs=costs, capex=capex, loans=loans, tax=tax)


DEFAULT_SALES_PLAN = SalesPlan(
    items=[
        SalesItem(
            channel="オンライン",
            product="主力製品",
            monthly=MonthlySeries(amounts=[Decimal("80000000")] * 12),
        ),
    ]
)

DEFAULT_COST_PLAN = CostPlan(
    variable_ratios={
        "COGS_MAT": Decimal("0.25"),
        "COGS_LBR": Decimal("0.06"),
        "COGS_OUT_SRC": Decimal("0.10"),
        "COGS_OUT_CON": Decimal("0.04"),
        "COGS_OTH": Decimal("0.00"),
    },
    fixed_costs={
        "OPEX_H": Decimal("170000000"),
        "OPEX_K": Decimal("468000000"),
        "OPEX_DEP": Decimal("6000000"),
    },
    non_operating_income={
        "NOI_MISC": Decimal("100000"),
    },
    non_operating_expenses={
        "NOE_INT": Decimal("7400000"),
    },
)

DEFAULT_CAPEX_PLAN = CapexPlan(items=[])
DEFAULT_LOAN_SCHEDULE = LoanSchedule(loans=[])
DEFAULT_TAX_POLICY = TaxPolicy()
