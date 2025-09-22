from datetime import datetime
from decimal import Decimal
import unittest

from models import EstimateRange
from services.fermi_learning import range_profile_from_estimate, update_learning_state


class RangeProfileTests(unittest.TestCase):
    def test_range_profile_scaling(self) -> None:
        estimate = EstimateRange(
            minimum=Decimal("100"),
            typical=Decimal("200"),
            maximum=Decimal("400"),
        )
        profile = range_profile_from_estimate(estimate, Decimal("100"))
        self.assertEqual(profile["min"], 1.0)
        self.assertEqual(profile["typical"], 2.0)
        self.assertEqual(profile["max"], 4.0)

        profile_zero = range_profile_from_estimate(estimate, Decimal("0"))
        self.assertEqual(profile_zero["min"], 100.0)

    def test_range_profile_invalid(self) -> None:
        with self.assertRaises(TypeError):
            range_profile_from_estimate("not-range", Decimal("1"))  # type: ignore[arg-type]


class LearningStateTests(unittest.TestCase):
    def test_update_learning_state_appends_history(self) -> None:
        now = datetime(2024, 1, 1, 0, 0, 0)

        state = update_learning_state(
            {},
            Decimal("100"),
            Decimal("120"),
            now=lambda: now,
        )

        self.assertIn("history", state)
        self.assertEqual(len(state["history"]), 1)
        entry = state["history"][0]
        self.assertEqual(entry["plan"], 100.0)
        self.assertEqual(entry["actual"], 120.0)
        self.assertAlmostEqual(entry["ratio"], 1.2)
        self.assertAlmostEqual(state["avg_ratio"], 1.2)
        self.assertEqual(entry["timestamp"], now.isoformat())

    def test_update_learning_state_limits_history_and_average(self) -> None:
        base_history = [
            {
                "plan": 100.0,
                "actual": 100.0,
                "ratio": 1.0,
                "diff": 0.0,
                "timestamp": f"t{i}",
            }
            for i in range(11)
        ]
        state = {"history": base_history, "avg_ratio": 1.0}

        updated = update_learning_state(
            state,
            Decimal("200"),
            Decimal("100"),
            now=lambda: datetime(2024, 1, 2),
        )

        self.assertEqual(len(updated["history"]), 12)
        self.assertAlmostEqual(updated["avg_ratio"], (11 * 1.0 + 0.5) / 12)

        # Add a 13th entry to ensure the oldest record is discarded
        updated_again = update_learning_state(
            updated,
            Decimal("300"),
            Decimal("450"),
            now=lambda: datetime(2024, 1, 3),
        )
        self.assertEqual(len(updated_again["history"]), 12)
        self.assertEqual(updated_again["history"][0]["timestamp"], "t1")

    def test_update_learning_state_ignores_non_positive(self) -> None:
        state = {"history": [{"ratio": 2.0}]}
        unchanged = update_learning_state(state, Decimal("0"), Decimal("100"))
        self.assertEqual(unchanged, state)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
