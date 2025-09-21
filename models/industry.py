"""Industry specific starter templates for inputs and analytics."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Tuple


@dataclass(frozen=True)
class IndustrySalesRow:
    """Definition of an illustrative sales line used in templates."""

    channel: str
    product: str
    customers: float
    unit_price: float
    frequency: float
    memo: str = ""
    monthly_pattern: Tuple[float, ...] = (1.0,) * 12

    def normalized_pattern(self) -> Tuple[float, ...]:
        total = sum(self.monthly_pattern)
        if not total:
            return (1.0 / 12,) * 12
        return tuple(value / total for value in self.monthly_pattern)


@dataclass(frozen=True)
class IndustryTemplate:
    """Collection of defaults for a specific industry profile."""

    key: str
    label: str
    description: str
    sales_rows: Tuple[IndustrySalesRow, ...]
    variable_ratios: Dict[str, float]
    fixed_costs: Dict[str, float]
    non_operating_income: Dict[str, float] = field(default_factory=dict)
    non_operating_expenses: Dict[str, float] = field(default_factory=dict)
    working_capital: Dict[str, float] = field(
        default_factory=lambda: {
            "receivable_days": 45.0,
            "inventory_days": 30.0,
            "payable_days": 25.0,
        }
    )
    custom_metrics: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def suggested_kpis(self) -> List[str]:
        return list(self.custom_metrics.keys())


def _pattern_from(values: Iterable[float]) -> Tuple[float, ...]:
    seq = tuple(values)
    if len(seq) != 12:
        raise ValueError("月次パターンは12項目で指定してください。")
    return seq


INDUSTRY_TEMPLATES: Dict[str, IndustryTemplate] = {}


def _register(template: IndustryTemplate) -> None:
    INDUSTRY_TEMPLATES[template.key] = template


_register(
    IndustryTemplate(
        key="manufacturing",
        label="製造業", 
        description="法人向け製造業を想定。材料費が高めで売掛金回収は60日程度を想定。",
        sales_rows=(
            IndustrySalesRow(
                channel="法人営業",
                product="主力製品A",
                customers=24,
                unit_price=850000.0,
                frequency=1.0,
                memo="四半期ごとの大量受注。",
                monthly_pattern=_pattern_from([1.2, 0.8, 1.0, 1.3, 0.9, 1.1, 1.0, 1.0, 1.2, 1.3, 1.4, 1.8]),
            ),
            IndustrySalesRow(
                channel="代理店",
                product="補完部材",
                customers=40,
                unit_price=180000.0,
                frequency=1.0,
                memo="代理店経由の保守パーツ。",
                monthly_pattern=_pattern_from([1.0] * 12),
            ),
        ),
        variable_ratios={
            "COGS_MAT": 0.42,
            "COGS_LBR": 0.08,
            "COGS_OUT_SRC": 0.06,
            "COGS_OUT_CON": 0.03,
            "COGS_OTH": 0.01,
        },
        fixed_costs={
            "OPEX_H": 9500000.0,
            "OPEX_K": 7200000.0,
            "OPEX_DEP": 4200000.0,
        },
        non_operating_expenses={
            "NOE_INT": 2500000.0,
        },
        working_capital={
            "receivable_days": 60.0,
            "inventory_days": 45.0,
            "payable_days": 35.0,
        },
        custom_metrics={
            "稼働率": {"type": "frequency", "target": 2.0},
            "受注単価": {"type": "unit_price"},
        },
    )
)

_register(
    IndustryTemplate(
        key="services",
        label="サービス業",
        description="プロフェッショナルサービス/コンサルティングを想定。人件費比率が高い。",
        sales_rows=(
            IndustrySalesRow(
                channel="直販",
                product="顧問契約",
                customers=15,
                unit_price=600000.0,
                frequency=1.0,
                memo="年間顧問契約。",
                monthly_pattern=_pattern_from([1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.2, 1.3, 1.4, 1.6]),
            ),
            IndustrySalesRow(
                channel="紹介",
                product="スポットプロジェクト",
                customers=8,
                unit_price=950000.0,
                frequency=0.5,
                memo="四半期で2件程度のプロジェクト。",
                monthly_pattern=_pattern_from([0.6, 0.6, 0.9, 1.1, 0.8, 1.2, 0.9, 1.0, 1.1, 1.2, 1.4, 1.8]),
            ),
        ),
        variable_ratios={
            "COGS_MAT": 0.05,
            "COGS_LBR": 0.18,
            "COGS_OUT_SRC": 0.07,
            "COGS_OUT_CON": 0.02,
            "COGS_OTH": 0.02,
        },
        fixed_costs={
            "OPEX_H": 12500000.0,
            "OPEX_K": 5400000.0,
            "OPEX_DEP": 1800000.0,
        },
        non_operating_income={
            "NOI_MISC": 600000.0,
        },
        working_capital={
            "receivable_days": 45.0,
            "inventory_days": 15.0,
            "payable_days": 20.0,
        },
        custom_metrics={
            "平均契約単価": {"type": "unit_price"},
            "稼働率": {"type": "frequency", "target": 1.5},
        },
    )
)

_register(
    IndustryTemplate(
        key="restaurant",
        label="飲食業",
        description="店舗型飲食業を想定。Fermi推定として原価率30%を自動設定。",
        sales_rows=(
            IndustrySalesRow(
                channel="店舗",
                product="ランチ",
                customers=3600,
                unit_price=1200.0,
                frequency=1.0,
                memo="平日中心のランチ需要。",
                monthly_pattern=_pattern_from([0.9, 0.9, 1.0, 1.1, 1.1, 1.1, 1.2, 1.3, 1.2, 1.1, 1.0, 0.9]),
            ),
            IndustrySalesRow(
                channel="店舗",
                product="ディナー",
                customers=2200,
                unit_price=3200.0,
                frequency=1.0,
                memo="週末の宴会ニーズ。",
                monthly_pattern=_pattern_from([0.8, 0.9, 1.0, 1.0, 1.1, 1.2, 1.3, 1.3, 1.4, 1.4, 1.1, 0.8]),
            ),
        ),
        variable_ratios={
            "COGS_MAT": 0.24,
            "COGS_LBR": 0.03,
            "COGS_OUT_SRC": 0.01,
            "COGS_OUT_CON": 0.01,
            "COGS_OTH": 0.01,
        },
        fixed_costs={
            "OPEX_H": 7800000.0,
            "OPEX_K": 5200000.0,
            "OPEX_DEP": 900000.0,
        },
        non_operating_expenses={
            "NOE_INT": 1200000.0,
        },
        working_capital={
            "receivable_days": 5.0,
            "inventory_days": 20.0,
            "payable_days": 18.0,
        },
        custom_metrics={
            "来店客数": {"type": "customers"},
            "客単価": {"type": "unit_price"},
            "席稼働率": {"type": "frequency", "target": 1.2},
        },
    )
)

_register(
    IndustryTemplate(
        key="ecommerce",
        label="EC",
        description="自社EC/サブスク型のD2Cを想定。年末商戦で売上がピーク。",
        sales_rows=(
            IndustrySalesRow(
                channel="自社EC",
                product="定期購入",
                customers=1800,
                unit_price=6800.0,
                frequency=1.0,
                memo="毎月継続利用する既存顧客。",
                monthly_pattern=_pattern_from([1.0, 1.0, 1.0, 1.0, 1.05, 1.05, 1.1, 1.15, 1.2, 1.25, 1.4, 1.6]),
            ),
            IndustrySalesRow(
                channel="マーケットプレイス",
                product="スポット販売",
                customers=4200,
                unit_price=5200.0,
                frequency=0.7,
                memo="キャンペーンでのスポット販売。",
                monthly_pattern=_pattern_from([0.8, 0.9, 0.9, 1.0, 1.0, 1.1, 1.1, 1.2, 1.3, 1.5, 1.8, 2.2]),
            ),
        ),
        variable_ratios={
            "COGS_MAT": 0.28,
            "COGS_LBR": 0.05,
            "COGS_OUT_SRC": 0.05,
            "COGS_OUT_CON": 0.03,
            "COGS_OTH": 0.02,
        },
        fixed_costs={
            "OPEX_H": 6900000.0,
            "OPEX_K": 8600000.0,
            "OPEX_DEP": 1500000.0,
        },
        non_operating_income={
            "NOI_MISC": 400000.0,
        },
        working_capital={
            "receivable_days": 25.0,
            "inventory_days": 35.0,
            "payable_days": 28.0,
        },
        custom_metrics={
            "平均注文単価": {"type": "unit_price"},
            "再購入率": {"type": "frequency", "target": 1.0},
        },
    )
)


__all__ = ["IndustryTemplate", "IndustrySalesRow", "INDUSTRY_TEMPLATES"]
