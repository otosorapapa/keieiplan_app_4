from decimal import Decimal
import math
import unittest

from ui.fermi import compute_fermi_estimate


class FermiEstimateTests(unittest.TestCase):
    def test_compute_fermi_estimate_balances_ranges(self) -> None:
        estimate = compute_fermi_estimate(
            daily_visitors=(50, 60, 80),
            unit_price=(1000, 1200, 1500),
            business_days=(20, 22, 25),
            seasonal_key="均等",
        )

        typical_monthly = 60 * 1200 * 22
        self.assertEqual(len(estimate.monthly), 12)
        self.assertTrue(all(value >= 0 for value in estimate.monthly))
        self.assertTrue(all(value >= 0 for value in estimate.monthly_min))
        self.assertTrue(all(value >= 0 for value in estimate.monthly_max))
        self.assertTrue(estimate.annual_min <= estimate.annual_typical <= estimate.annual_max)
        self.assertTrue(
            math.isclose(
                estimate.annual_typical,
                float(typical_monthly) * 12,
                rel_tol=1e-6,
            )
        )

        adjusted = estimate.typical_with_ratio(0.5)
        self.assertEqual(len(adjusted), 12)
        self.assertTrue(all(math.isclose(val, base * 0.5) for val, base in zip(adjusted, estimate.monthly)))

    def test_seasonal_pattern_normalisation(self) -> None:
        estimate = compute_fermi_estimate(
            daily_visitors=(20, 40, 50),
            unit_price=(500, 600, 700),
            business_days=(10, 20, 30),
            seasonal_key="繁忙期(Q4)",
        )
        # Normalisation ensures total annual equals 12 times the baseline monthly figure.
        baseline = 40 * 600 * 20
        self.assertTrue(
            math.isclose(
                estimate.annual_typical,
                float(baseline) * 12,
                rel_tol=1e-6,
            )
        )
        self.assertNotEqual(estimate.monthly[0], estimate.monthly[-1])  # seasonality applied


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
