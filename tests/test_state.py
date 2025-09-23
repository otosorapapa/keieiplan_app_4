from __future__ import annotations

import unittest

import streamlit as st

from models import CapexPlan, LoanSchedule
from state import load_finance_bundle


class LoadFinanceBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        st.session_state.clear()

    def tearDown(self) -> None:
        st.session_state.clear()

    def test_loads_bundle_from_raw_mappings(self) -> None:
        st.session_state["finance_models"] = {
            "sales": {"items": []},
            "costs": {
                "variable_ratios": {},
                "fixed_costs": {},
                "gross_linked_ratios": {},
                "non_operating_income": {},
                "non_operating_expenses": {},
            },
            "capex": {
                "items": [
                    {
                        "name": "設備投資",
                        "amount": "500000",
                        "start_month": 1,
                        "useful_life_years": 5,
                    }
                ]
            },
            "loans": {
                "loans": [
                    {
                        "name": "メインバンク",
                        "principal": "1200000",
                        "interest_rate": "0.05",
                        "term_months": 12,
                        "start_month": 1,
                        "repayment_type": "equal_principal",
                    }
                ]
            },
            "tax": {
                "corporate_tax_rate": "0.30",
                "business_tax_rate": "0.05",
                "consumption_tax_rate": "0.10",
                "dividend_payout_ratio": "0.0",
            },
        }

        bundle, is_custom = load_finance_bundle()

        self.assertTrue(is_custom)
        self.assertIsInstance(bundle.capex, CapexPlan)
        self.assertGreater(len(bundle.capex.payment_schedule()), 0)
        self.assertIsInstance(bundle.loans, LoanSchedule)
        self.assertGreater(len(bundle.loans.amortization_schedule()), 0)

        models_state = st.session_state.get("finance_models", {})
        self.assertIsInstance(models_state.get("capex"), CapexPlan)
        self.assertIsInstance(models_state.get("loans"), LoanSchedule)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
