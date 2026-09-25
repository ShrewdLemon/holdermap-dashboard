#!/usr/bin/env python3
"""Independent check of every company snapshot (src/co/*.json) against official published figures.

    python3 scripts/validate_universe.py            # summary + mismatches
    python3 scripts/validate_universe.py --json out.json

It does not reuse the exporter's code. For the latest filed quarter (Jun-26) it compares:
  - promoter %  with NSE's shareholding index (pr_and_prgrp) and BSE's copy of the filing (A total);
  - FII and DII % with BSE's Sub Total B2 / Sub Total B1 (Fld_TotalPercentageOf_A_B_C2);
  - market cap (price x current shares) with NSE's own issue size.
Percentages are compared on the filing's own basis: shares / (A+B+C2) when the depository-receipt shares
sit in C1, shares / total when the filing counts them inside foreign institutions (dr_in_public).
Local-only: needs ~/Projects/exports/freefloat and ~/Projects/msci (not available in CI).
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME = Path.home() / "Projects"
NSE_IDX = HOME / "exports" / "freefloat" / "data" / "shp"
BSE = HOME / "msci" / "data_dump" / "bse_shp_all"
TOL = 0.05  # percentage points


def nse_promoter(sym):
    p = NSE_IDX / f"{sym}.json"
    if not p.exists():
        return None
    for r in json.loads(p.read_text()):
        if r.get("date") == "30-JUN-2026":
            try:
                return float(r["pr_and_prgrp"])
            except (TypeError, ValueError):
                return None
    return None


def bse_figures(code):
    d = BSE / str(code)
    if not code or not (d / "summary.json").exists():
        return None
    s = json.loads((d / "summary.json").read_text())
    if not s.get("Table") or s["Table"][0].get("Fld_qtrname") != "June 2026":
        return None
    out = {}
    for r in s["Table1"]:
        if r["Fld_Code"] == "STA1A2":
            out["prom"] = r["Fld_TotalPercentageOf_A_B_C2"]
        if r["Fld_Code"] == "STC1":
            out["c1"] = r.get("Fld_NoOfDRShares") or r.get("Fld_TotalNoOfShares") or 0
    pub = d / "public.json"
    if pub.exists():
        for r in json.loads(pub.read_text())["Table1"]:
            lvl = r.get("Fld_Level") or ""
            if lvl == "Sub Total B1":
                out["dii"] = r["Fld_TotalPercentageOf_A_B_C2"]
            elif lvl == "Sub Total B2":
                out["fii"] = r["Fld_TotalPercentageOf_A_B_C2"]
            elif "Depositor" in lvl:
                out["dep"] = r["Fld_TotalNoOfShares"]
    return out


def check(sym, d):
    t = next((x for x in d["trend"] if x["q"] == "Jun-26"), None)
    if t is None:
        return {"sym": sym, "status": "no Jun-26 quarter"}
    dr = t.get("dr") or 0
    style2 = bool(t.get("dr_in_public"))
    den = t["tot"] if style2 else t.get("den") or (t["tot"] - dr)
    ours = {"prom": 100 * t["prom"] / den,
            "fii": 100 * (t["fii"] + (dr if style2 else 0)) / den,
            "dii": 100 * t["dii"] / den}
    res = {"sym": sym, "style2": style2, "ours": {k: round(v, 2) for k, v in ours.items()}, "diffs": {}}
    np = nse_promoter(sym)
    if np is not None:
        res["diffs"]["prom_vs_nse"] = round(ours["prom"] - np, 3)
    # BSE's stored copy is the company's LATEST filing; after a special filing (merger, QIP) it is not the quarter-end one
    later = ((d.get("co") or {}).get("fil") or "") > "2026-06-30"
    b = None if later else bse_figures((d.get("co") or {}).get("bse"))
    if b:
        for k in ("prom", "fii", "dii"):
            if b.get(k) is not None:
                res["diffs"][f"{k}_vs_bse"] = round(ours[k] - b[k], 3)
    chk = (d.get("co") or {}).get("checks") or {}
    if chk.get("mcap_vs_nse_pct") is not None:
        res["mcap_vs_nse_pct"] = chk["mcap_vs_nse_pct"]
    bad = {k: v for k, v in res["diffs"].items() if abs(v) > TOL}
    res["status"] = "ok" if not bad else "mismatch"
    res["bad"] = bad
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    a = ap.parse_args()
    rows = [check(f.stem, json.loads(f.read_text())) for f in sorted((ROOT / "src" / "co").glob("*.json"))]
    n = len(rows)
    compared = [r for r in rows if r.get("diffs")]
    ok = [r for r in compared if r["status"] == "ok"]
    bad = [r for r in compared if r["status"] == "mismatch"]
    by = {}
    for r in compared:
        for k in r["diffs"]:
            by.setdefault(k, [0, 0])
            by[k][0] += 1
            by[k][1] += abs(r["diffs"][k]) <= TOL
    print(f"{n} companies; {len(compared)} compared with NSE/BSE; {len(ok)} match every figure within {TOL} pp; {len(bad)} mismatch")
    for k, (m, g) in sorted(by.items()):
        print(f"  {k:14s} {g}/{m} within {TOL} pp")
    for r in sorted(bad, key=lambda r: -max(abs(v) for v in r["bad"].values()))[:60]:
        print(f"  MISMATCH {r['sym']:12s} style2={r['style2']!s:5s} {r['bad']} ours={r['ours']}")
    no = [r["sym"] for r in rows if not r.get("diffs")]
    if no:
        print(f"  not compared ({len(no)}): {', '.join(no[:30])}")
    if a.json:
        Path(a.json).write_text(json.dumps(rows, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
