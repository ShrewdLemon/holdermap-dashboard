import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
import live  # noqa: E402


class LiveTest(unittest.TestCase):
    def test_bonus_factor(self):
        self.assertEqual(live.factor("2025-03-04"), 4)
        self.assertEqual(live.factor("2025-03-05"), 2)
        self.assertEqual(live.factor("2026-06-03"), 1)

    def test_dates(self):
        self.assertEqual(live.months_back(dt.date(2026, 3, 31), 1), dt.date(2026, 2, 28))
        self.assertEqual(live.quarter_start(dt.date(2026, 9, 23)), dt.date(2026, 7, 1))

    def test_offline_build_matches_snapshot(self):
        live.CACHE = Path(tempfile.mkdtemp()) / "closes.json"
        px = live.build(dt.date(2026, 9, 23), offline=True)
        self.assertEqual(px["now"]["d"], "2026-09-23")
        self.assertEqual(px["now"]["c"], 2169.2)
        self.assertEqual({b["k"] for b in px["bases"]}, {"1m", "3m", "6m", "ytd", "1y", "3y", "sl"})
        sl = next(b for b in px["bases"] if b["k"] == "sl")
        self.assertAlmostEqual(sl["s"], 583.55 / 4, places=3)


if __name__ == "__main__":
    unittest.main()
