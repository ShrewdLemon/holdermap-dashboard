"""Regression gate: pipeline/company.py must reproduce the hand-built ANANDRATHI snapshot (src/data.json).

    python3 -m unittest tests.test_company -v

Compared to 0.01: tot, ff, trend, fii, dii, ind, flows, prices, px, px_series (on the overlap), fii/dii totals,
w52 and the return anchors. The only accepted differences are where data.json carried hand-typed or
pre-bhavcopy values:
  * prices[5] (open quarter): data.json kept the run's 22-Sep close (2179.0, 'quarter still open on 2026-09-22');
    company.py uses the 23-Sep bhavcopy close (2169.2) - the same close data.json itself used for px[5].
  * stock_anchor['2026-08-21'][3]: data.json labelled that close 'stockanalysis.com' (bhavcopy.db then lacked
    10 Aug-22 Sep 2026); the value is identical and now comes from NSE bhavcopy.
  * gates[].ok is new (added for the app).
"""
import json
import sys
from pathlib import Path

import unittest

ROOT = Path(__file__).resolve().parent.parent
_LOCAL = [Path.home() / "Projects" / "msci" / "data_dump" / "bhavcopy.db",
          Path.home() / "Projects" / "nse100-holders" / "companies" / "ANANDRATHI" / "run.json"]
if not all(p.exists() for p in _LOCAL):     # CI (CodeBuild) has none of the local market data
    raise unittest.SkipTest("local market data absent (msci bhavcopy.db / nse100-holders); regression gate skipped")
sys.path.insert(0, str(ROOT / "pipeline"))
import company  # noqa: E402

# frozen copy of the hand-built src/data.json (ANANDRATHI v1), so the gate survives data.json changing
OLD = json.loads((ROOT / "tests" / "fixtures" / "ANANDRATHI_data_v1.json").read_text())


def diff(a, b, path=""):
    if isinstance(a, dict) and isinstance(b, dict):
        out = [f"{path}.{k} missing" for k in set(a) ^ set(b)]
        for k in set(a) & set(b):
            out += diff(a[k], b[k], f"{path}.{k}")
        return out
    if isinstance(a, list) and isinstance(b, list):
        out = [f"{path} len {len(a)} != {len(b)}"] if len(a) != len(b) else []
        for i, (x, y) in enumerate(zip(a, b)):
            out += diff(x, y, f"{path}[{i}]")
        return out
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return [] if abs(a - b) <= 0.01 else [f"{path}: {a} != {b}"]
    return [] if a == b else [f"{path}: {a!r} != {b!r}"]


KEYS = ["tot", "ff", "px", "hq", "trend", "fii", "dii", "ind", "flows", "tiers", "rec", "flag", "fii_total",
        "dii_total", "w52"]


class CompanyRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.new, cls.info, cls.pxu = company.build(company.Ctx(), "ANANDRATHI")

    def test_same(self):
        for key in KEYS:
            with self.subTest(key=key):
                new = self.new[key]
                if key == "trend":            # dr/den/drp/c2 are additions (DR-aware denominator)
                    new = [{k: v for k, v in t.items() if k in OLD["trend"][0]} for t in new]
                self.assertEqual(diff(OLD[key], new, key), [])

    def test_den(self):
        for t in self.new["trend"]:           # ANANDRATHI has no depository receipts
            self.assertEqual((t["dr"], t["den"], t["dr_in_public"]), (0, t["tot"], False))
            self.assertEqual(t["prom"] + t["fii"] + t["dii"] + t["ind"] + t["oth"] + t["dr"], t["tot"])
        c = self.new["co"]["checks"]
        self.assertTrue(c["prom_vs_nse"])     # 41.37% = NSE's published pr_and_prgrp

    def test_prices(self):
        self.assertEqual(diff(OLD["prices"][:5], self.new["prices"][:5], "prices"), [])
        p = self.new["prices"][5]
        self.assertEqual((p["d"], p["c"], p["a"], p["f"]), ("2026-09-23", 2169.2, 2169.2, 1.0))
        self.assertEqual(p["c"], OLD["px"][5])

    def test_gates(self):
        self.assertEqual([dict(n=g["n"], d=g["d"]) for g in self.new["gates"]], OLD["gates"])
        self.assertTrue(all(g["ok"] for g in self.new["gates"]))

    def test_px_series(self):
        old = {r[0]: r for r in OLD["px_series"]}
        got = {r[0]: r for r in self.new["px_series"]}
        self.assertTrue(set(old) <= set(got))
        for d, r in old.items():
            self.assertTrue(all(abs(x - y) <= 0.01 for x, y in zip(r[1:], got[d][1:])), (d, r, got[d]))
        self.assertEqual(self.new["px_series"][-1][0], company.END)
        self.assertGreaterEqual(self.new["px_series"][0][0], "2025-08-23")

    def test_anchors(self):
        for k, v in OLD["stock_anchor"].items():
            n = self.new["stock_anchor"][k]
            self.assertTrue(n[0] == v[0] and abs(n[1] - v[1]) <= 0.0001 and abs(n[2] - v[2]) <= 0.001, (k, v, n))
        self.assertEqual(self.new["px_hist"]["listing"], ["2021-12-14", 145.8875, 583.55])

    def test_checks(self):
        c = self.new["co"]["checks"]
        self.assertTrue(c["checksum"])
        self.assertLess(abs(c["mcap_vs_nse_pct"]), 1)
        self.assertTrue(self.new["co"]["oq"] and self.new["co"]["bb"])
        self.assertEqual(self.new["co"]["ca"], [["2025-03-05", 2.0, "bonus"], ["2026-06-03", 2.0, "bonus"]])
        self.assertEqual(self.new["co"]["shares_now"], 166041268)
        self.assertEqual(self.pxu["shares"], 166041268)
        self.assertEqual(self.pxu["qbase_close"], 1976.7)


if __name__ == "__main__":
    unittest.main()
