import unittest
from decimal import Decimal

from calc import generate_cash_flow
from models import CapexItem, CapexPlan, LoanItem, LoanSchedule, TaxPolicy


class CashFlowGenerationTests(unittest.TestCase):
    def test_generate_cash_flow_returns_schedule_and_metrics(self) -> None:
        capex_plan = CapexPlan(
            items=[
                CapexItem(
                    name="Factory Equipment",
                    amount=Decimal("100000"),
                    start_month=1,
                    useful_life_years=5,
                )
            ]
        )
        loan_schedule = LoanSchedule(
            loans=[
                LoanItem(
                    name="Bank Loan",
                    principal=Decimal("60000"),
                    interest_rate=Decimal("0.06"),
                    term_months=12,
                    start_month=1,
                )
            ]
        )
        tax_policy = TaxPolicy(corporate_tax_rate=Decimal("0.30"))

        pl_amounts = {"ORD": Decimal("50000"), "OPEX_DEP": Decimal("20000")}

        result = generate_cash_flow(pl_amounts, capex_plan, loan_schedule, tax_policy)

        self.assertIn("loan_schedule", result)
        amortization = loan_schedule.amortization_schedule()
        self.assertEqual(len(result["loan_schedule"]), len(amortization))
        self.assertEqual(result["投資キャッシュフロー"], Decimal("-100000"))

        first_year_principal = sum(entry.principal for entry in amortization if entry.year == 1)
        self.assertEqual(result["財務キャッシュフロー"], -first_year_principal)

        interest_first_year = sum(entry.interest for entry in amortization if entry.year == 1)
        expected_operating_pre_interest = result["営業キャッシュフロー"] + interest_first_year
        self.assertAlmostEqual(
            float(result["営業キャッシュフロー（利払前）"]),
            float(expected_operating_pre_interest),
            places=6,
        )

        metrics = result.get("investment_metrics", {})
        self.assertIn("npv", metrics)
        self.assertIn("payback_period_years", metrics)
        self.assertIsNotNone(metrics.get("payback_period_years"))
        monthly_cash_flows = metrics.get("monthly_cash_flows", [])
        self.assertEqual(len(monthly_cash_flows), 120)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
