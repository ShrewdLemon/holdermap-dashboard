#!/usr/bin/env python3
"""NIFTY 50 and NIFTY 500 daily PRICE index closes, inception -> END.

    python3 pipeline/index_hist.py            # fetch missing years, write JSON, cross-check
    python3 pipeline/index_hist.py --check    # cross-check only (no network)

Source: niftyindices.com historical data (NSE Indices Ltd), the same session
pattern as arwl-workstation/research/pipeline/fetch_tri.py:
  GET  https://www.niftyindices.com/reports/historical-data   (cookies)
  POST https://www.niftyindices.com/BackPage/getHistoricaldatatabletoString
       {"cinfo": "{'name':'NIFTY 50','startDate':'01-Jan-1996','endDate':'31-Dec-1996','indexName':'NIFTY 50'}"}
The endpoint refuses ranges wider than 365 days, so history is walked one
calendar year per request, ~1 request/s, and the run STOPS at the first block
(HTTP 403, or an HTML body where JSON belongs - the endpoint answers with
content-type text/html even when the body is JSON, so the body is parsed).

Raw yearly responses are kept in cache/index_hist_raw/ so a rerun only asks for
years it does not hold (the current year is always refetched).

Writes pipeline/inputs/index_hist.json:
  {"n50": {"YYYY-MM-DD": close}, "n500": {...}, "src": "...", "first": {"n50": d, "n500": d}}
and cross-checks against NSE's own ind_close_all_DDMMYYYY.csv closes that
pipeline/live.py already cached in cache/closes.json (exact match required).
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RAW = ROOT / "cache" / "index_hist_raw"
OUT = HERE / "inputs" / "index_hist.json"
CLOSES = ROOT / "cache" / "closes.json"          # written by pipeline/live.py (read-only here)
EXTRA_CHECK = [Path.home() / "Projects" / "netra" / "docs" / "empirical" / "phase1" /
               "tri-usdinr-sources" / "raw" / "ind_close_all_11092026.csv"]
PAGE = "https://www.niftyindices.com/reports/historical-data"
API = "https://www.niftyindices.com/BackPage/getHistoricaldatatabletoString"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
INDICES = {"n50": "NIFTY 50", "n500": "NIFTY 500"}
FIRST_YEAR = 1990          # probe from here; empty years before inception come back []
END = date(2026, 9, 24)
PAUSE = 1.1
COOKIES = RAW / "cookies.txt"


class Blocked(Exception):
    pass


def _curl(args, timeout=90):
    r = subprocess.run(["curl", "-sS", "-m", str(timeout), "-A", UA,
                        "-c", str(COOKIES), "-b", str(COOKIES), "-w", "\n%{http_code}"] + args,
                       capture_output=True, timeout=timeout + 30)
    raw = r.stdout
    nl = raw.rfind(b"\n")
    try:
        code = int(raw[nl + 1:].strip() or 0)
    except ValueError:
        code = 0
    return code, raw[:nl] if nl >= 0 else raw


def open_session():
    code, body = _curl([PAGE])
    if code != 200 or b"<html" not in body[:3000].lower():
        raise Blocked(f"session page HTTP {code}")


def fetch_year(name, y):
    start = date(y, 1, 1)
    end = min(date(y, 12, 31), END)
    cinfo = ("{'name':'%s','startDate':'%s','endDate':'%s','indexName':'%s'}"
             % (name, start.strftime("%d-%b-%Y"), end.strftime("%d-%b-%Y"), name))
    code, body = _curl(["-X", "POST", API,
                        "-H", "Accept: application/json, text/javascript, */*; q=0.01",
                        "-H", "Content-Type: application/json; charset=utf-8",
                        "-H", f"Referer: {PAGE}",
                        "-H", "X-Requested-With: XMLHttpRequest",
                        "--data", json.dumps({"cinfo": cinfo})])
    try:
        rows = json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        rows = None
    if code in (401, 403) or rows is None or not isinstance(rows, list):
        raise Blocked(f"{name} {y}: HTTP {code}, body {body[:80]!r}")
    return rows


def parse_rows(rows, name):
    out = {}
    for r in rows:
        if (r.get("INDEX_NAME") or "").strip().upper() != name.upper():
            continue
        d = datetime.strptime(r["HistoricalDate"].strip(), "%d %b %Y").date()
        c = float(str(r["CLOSE"]).replace(",", ""))
        out[d.isoformat()] = c
    return out


def fetch_all(log):
    RAW.mkdir(parents=True, exist_ok=True)
    got = {k: {} for k in INDICES}
    session = False
    calls = 0
    for key, name in INDICES.items():
        seen_data = False
        for y in range(FIRST_YEAR, END.year + 1):
            p = RAW / f"{key}_{y}.json"
            if p.exists() and y < END.year:
                rows = json.loads(p.read_text())
            else:
                if not session:
                    open_session()
                    session = True
                    time.sleep(PAUSE)
                rows = fetch_year(name, y)
                calls += 1
                p.write_text(json.dumps(rows))
                time.sleep(PAUSE)
            vals = parse_rows(rows, name)
            if vals:
                seen_data = True
            elif seen_data:
                log(f"  WARNING {name} {y}: no rows after data had started")
            got[key].update(vals)
            if vals and y not in (END.year,) and len(vals) < 150 and \
                    min(vals) > f"{y}-01-31":
                log(f"  note {name} {y}: {len(vals)} rows, first {min(vals)} (inception year?)")
    return got, calls


def reference_closes():
    """date -> {"n50": x, "n500": y} from NSE ind_close_all files already on disk."""
    ref = {}
    if CLOSES.exists():
        for d, v in json.loads(CLOSES.read_text()).items():
            if isinstance(v, dict) and v.get("ix"):
                ref[d] = {k: v["ix"][k] for k in ("n50", "n500") if v["ix"].get(k) is not None}
    for p in EXTRA_CHECK:
        if not p.exists():
            continue
        d = datetime.strptime(p.stem.split("_")[-1], "%d%m%Y").date().isoformat()
        for r in csv.DictReader(p.open()):
            nm = (r.get("Index Name") or "").strip().lower()
            k = {"nifty 50": "n50", "nifty 500": "n500"}.get(nm)
            if k:
                ref.setdefault(d, {})[k] = float(r["Closing Index Value"])
    return ref


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="cross-check the written JSON only")
    a = ap.parse_args()
    log = print
    t0 = time.time()
    if not a.check:
        try:
            got, calls = fetch_all(log)
        except Blocked as b:
            sys.exit(f"STOPPED - niftyindices refused: {b}")
        out = {
            "n50": dict(sorted(got["n50"].items())),
            "n500": dict(sorted(got["n500"].items())),
            "src": ("niftyindices.com (NSE Indices Ltd) historical data, price index CLOSE: "
                    "POST /BackPage/getHistoricaldatatabletoString, one calendar year per "
                    f"request; fetched {date.today().isoformat()}; raw responses in "
                    "cache/index_hist_raw/"),
            "first": {k: min(v) for k, v in got.items() if v},
        }
        OUT.write_text(json.dumps(out, separators=(",", ":")))
        log(f"wrote {OUT.relative_to(ROOT)}: n50 {len(out['n50'])} days "
            f"({out['first'].get('n50')} -> {max(out['n50'])}), n500 {len(out['n500'])} days "
            f"({out['first'].get('n500')} -> {max(out['n500'])}); {calls} live requests, "
            f"{time.time() - t0:.0f}s")
    d = json.loads(OUT.read_text())
    ref = reference_closes()
    n = bad = 0
    for day in sorted(ref):
        for k, v in ref[day].items():
            mine = d[k].get(day)
            n += 1
            ok = mine is not None and round(mine, 2) == round(v, 2)
            bad += not ok
            log(f"  {day} {k:4s} NSE ind_close_all {v:>10.2f}  niftyindices "
                f"{'MISSING' if mine is None else f'{mine:>10.2f}'}  {'ok' if ok else 'MISMATCH'}")
    log(f"cross-check: {n - bad}/{n} exact matches against NSE ind_close_all")
    if bad:
        sys.exit(1)


if __name__ == "__main__":
    main()
