from decimal import Decimal
import unittest

from models import CostPlan, EstimateRange, MonthlySeries, SalesItem, SalesPlan


class EstimateRangeTests(unittest.TestCase):
    def test_range_orders_and_addition(self) -> None:
        base = EstimateRange(minimum="300", typical="100", maximum="200")
        self.assertEqual(base.minimum, Decimal("100"))
        self.assertEqual(base.typical, Decimal("200"))
        self.assertEqual(base.maximum, Decimal("300"))

        other = EstimateRange(minimum="10", typical="20", maximum="40")
        combined = base + other
        self.assertEqual(combined.minimum, Decimal("110"))
        self.assertEqual(combined.typical, Decimal("220"))
        self.assertEqual(combined.maximum, Decimal("340"))

        scaled = other.scaled(Decimal("2"))
        self.assertEqual(scaled.minimum, Decimal("20"))
        self.assertEqual(scaled.typical, Decimal("40"))
        self.assertEqual(scaled.maximum, Decimal("80"))

        zero_scaled = other.scaled(Decimal("-1"))
        self.assertEqual(zero_scaled.minimum, Decimal("0"))
        self.assertEqual(zero_scaled.typical, Decimal("0"))
        self.assertEqual(zero_scaled.maximum, Decimal("0"))


class SalesPlanSummaryTests(unittest.TestCase):
    def test_assumption_summary_aggregates_ranges(self) -> None:
        item_one = SalesItem(
            channel="Online",
            product="Subscription",
            monthly=MonthlySeries(amounts=[Decimal("10")] * 12),
            customers=Decimal("100"),
            unit_price=Decimal("50"),
            purchase_frequency=Decimal("2"),
            revenue_range=EstimateRange(
                minimum=Decimal("100"),
                typical=Decimal("120"),
                maximum=Decimal("140"),
            ),
        )
        item_two = SalesItem(
            channel="Retail",
            product="Hardware",
            monthly=MonthlySeries(amounts=[Decimal("20")] * 12),
            customers=Decimal("50"),
            unit_price=Decimal("100"),
            purchase_frequency=Decimal("1"),
            revenue_range=EstimateRange(
                minimum=Decimal("200"),
                typical=Decimal("220"),
                maximum=Decimal("260"),
            ),
        )
        plan = SalesPlan(items=[item_one, item_two])

        summary = plan.assumption_summary()

        self.assertEqual(summary["total_sales"], Decimal("360"))
        self.assertEqual(summary["total_customers"], Decimal("150"))
        self.assertEqual(summary["total_transactions"], Decimal("250"))
        self.assertEqual(summary["avg_unit_price"], Decimal("60"))
        self.assertEqual(
            summary["avg_frequency"],
            Decimal("250") / Decimal("150"),
        )
        self.assertEqual(summary["range_min_total"], Decimal("300"))
        self.assertEqual(summary["range_typical_total"], Decimal("340"))
        self.assertEqual(summary["range_max_total"], Decimal("400"))


class CostPlanRangeTests(unittest.TestCase):
    def test_aggregate_range_totals(self) -> None:
        cost_plan = CostPlan(
            range_profiles={
                "COGS_MAT": EstimateRange(
                    minimum=Decimal("0.10"),
                    typical=Decimal("0.20"),
                    maximum=Decimal("0.30"),
                ),
                "OPEX_H": EstimateRange(
                    minimum=Decimal("100000"),
                    typical=Decimal("120000"),
                    maximum=Decimal("150000"),
                ),
                "NOE_INT": EstimateRange(
                    minimum=Decimal("10000"),
                    typical=Decimal("12000"),
                    maximum=Decimal("15000"),
                ),
            }
        )

        totals = cost_plan.aggregate_range_totals(Decimal("1000000"))
        self.assertEqual(totals["variable"].minimum, Decimal("100000"))
        self.assertEqual(totals["variable"].typical, Decimal("200000"))
        self.assertEqual(totals["variable"].maximum, Decimal("300000"))
        self.assertEqual(totals["fixed"].minimum, Decimal("100000"))
        self.assertEqual(totals["non_operating"].typical, Decimal("12000"))

        negative_totals = cost_plan.aggregate_range_totals(Decimal("-100"))
        self.assertEqual(negative_totals["variable"].minimum, Decimal("0"))
        self.assertEqual(negative_totals["variable"].typical, Decimal("0"))
        self.assertEqual(negative_totals["variable"].maximum, Decimal("0"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
