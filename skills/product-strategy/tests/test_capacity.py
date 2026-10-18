import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import capacity as C  # noqa: E402


class T(unittest.TestCase):
    def test_defaults(self):
        c = C.capacity({}, 6)
        self.assertEqual(c["hours_per_week"], 10.0)
        self.assertEqual(c["day_hours"], 8.0)
        self.assertAlmostEqual(c["dev_hours"], 10 * 26 * 0.7, delta=0.2)

    def test_from_survey_answer(self):
        c = C.capacity({"idea": {"facets": {"hours_week": 15}}}, 6)
        self.assertEqual(c["hours_per_week"], 15.0)
        self.assertIn("опрос", c["source"])
        # 15 ч/нед × 70 % ≈ 10.5 ч/нед ≈ 1.3 дня по 8 ч; за 6 мес ≈ 34 дня
        self.assertAlmostEqual(c["dev_days"], 34.1, delta=0.5)

    def test_explicit_wins(self):
        cfg = {"idea": {"facets": {"hours_week": 15}}, "project": {"capacity": {"hours_per_week": 20, "dev_share": 0.5, "day_hours": 6}}}
        c = C.capacity(cfg, 1)
        self.assertEqual((c["hours_per_week"], c["dev_share"], c["day_hours"]), (20.0, 0.5, 6.0))
        self.assertIn("6 ч", c["line"])

    def test_bad_values(self):
        c = C.capacity({"project": {"capacity": {"hours_per_week": "x", "dev_share": 5, "day_hours": -1}}}, 3)
        self.assertEqual(c["dev_share"], 1.0)
        self.assertEqual(c["day_hours"], 8.0)


if __name__ == "__main__":
    unittest.main()
