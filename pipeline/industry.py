#!/usr/bin/env python3
"""The exchanges' industry classification for every company: pipeline/inputs/industry.json.

    python3 pipeline/industry.py              # companies not yet on file
    python3 pipeline/industry.py --force      # everyone again (reclassifications are rare)
    python3 pipeline/industry.py --syms A,B   # just these
    python3 pipeline/industry.py --dry-run    # list what would be fetched

NSE and BSE classify listed companies on one four-level structure, harmonised between the two
exchanges (AMFI uses the same one for fund portfolios): macro-economic sector (12) > sector (22) >
industry (59) > basic industry (197). The landing page groups companies by sector and shows their
industry; company pages show the whole path.

Sources, one call at a time and at least 1.1 s apart; every response is checked before it is kept:
  1. NSE's quote API, www.nseindia.com/api/quote-equity?symbol=SYM, field industryInfo
     {macro, sector, industry, basicIndustry}. It is Akamai-protected (docs/PIPELINE.md, traps): the
     run stops at the first refusal, keeps what it has, and picks up from there next time.
  2. BSE's company header, api.bseindia.com/BseIndiaAPI/api/ComHeadernew/w?scripcode=CODE, fields
     Sector / IndustryNew / IGroup / ISubGroup (the same four levels), for companies NSE does not
     quote: BSE-only listings such as NSE itself.

Both hosts refuse cloud machines (they answered 403 from a cloud container on 25 Sep 2026), so run it
from the machine that runs pipeline/results.py. About 45 minutes for the whole universe at NSE's pace.

Until a company has a row here, build.py uses the sector in its company file (the "Industry" column of
NSE's index lists, which is the sector level) and the page shows its industry as not on file.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "pipeline" / "inputs" / "industry.json"
CACHE = ROOT / "cache" / "industry"
JAR = CACHE / "nse_cookies.txt"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
NSE_HOME = "https://www.nseindia.com/get-quotes/equity?symbol={sym}"
NSE_API = "https://www.nseindia.com/api/quote-equity?symbol={sym}"
BSE_API = "https://api.bseindia.com/BseIndiaAPI/api/ComHeadernew/w?quotetype=EQ&scripcode={code}&seriesid="
LEVELS = ("mac", "sec", "ind", "bi")  # macro-economic sector, sector, industry, basic industry
GAP = 1.1


class Refused(Exception):
    """The exchange answered with a block page or an auth error instead of data."""


def _curl(url, headers=(), cookies=False, timeout=30):
    cmd = ["curl", "-sS", "-L", "--compressed", "-m", str(timeout), "-A", UA, "-w", "\n%{http_code}"]
    if cookies:
        cmd += ["-b", str(JAR), "-c", str(JAR)]
    for h in headers:
        cmd += ["-H", h]
    r = subprocess.run(cmd + [url], capture_output=True, timeout=timeout + 30)
    raw = r.stdout
    nl = raw.rfind(b"\n")
    try:
        code = int(raw[nl + 1:].strip() or 0)
    except ValueError:
        code = 0
    return code, raw[:nl] if nl >= 0 else raw


def _refused(code, body):
    head = body[:300].lstrip().upper()
    return code in (401, 403, 429) or head.startswith(b"<") or b"ACCESS DENIED" in head


def _clean(v):
    v = (v or "").strip() if isinstance(v, str) else ""
    return "" if v in ("-", "NA", "N.A.", "null") else v


def nse_class(body: bytes):
    """[macro, sector, industry, basic industry] from NSE's quote JSON, or None if NSE has no classification."""
    try:
        j = json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        return None
    ii = j.get("industryInfo") if isinstance(j, dict) else None
    if not isinstance(ii, dict):
        return None
    vals = [_clean(ii.get(k)) for k in ("macro", "sector", "industry", "basicIndustry")]
    return vals if all(vals) else None


def bse_class(body: bytes):
    """The same four levels from BSE's company header JSON, or None."""
    try:
        j = json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        return None
    if not isinstance(j, dict):
        return None
    vals = [_clean(j.get(k)) for k in ("Sector", "IndustryNew", "IGroup", "ISubGroup")]
    return vals if all(vals) else None


def universe():
    """[(symbol, BSE scrip code or None, listed only on BSE?)] for every company page."""
    rows = json.loads((ROOT / "src" / "univ.json").read_text())
    extra = ROOT / "src" / "univ_extra.json"
    if extra.exists():
        rows += json.loads(extra.read_text())
    out = []
    for r in rows:
        p = ROOT / "src" / "co" / f"{r['s']}.json"
        co = json.loads(p.read_text()).get("co", {}) if p.exists() else {}
        code = (co.get("bse") or "").strip()
        out.append((r["s"], code if code.isdigit() and int(code) else None, (co.get("exch") or r.get("exch")) == "BSE"))
    return out


def load():
    return json.loads(OUT.read_text()) if OUT.exists() else {}


def save(rec):
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text("{\n" + ",\n".join(f"{json.dumps(k)}: {json.dumps(rec[k], ensure_ascii=False)}"
                                      for k in sorted(rec)) + "\n}\n")
    tmp.replace(OUT)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--syms", help="comma-separated symbols")
    ap.add_argument("--force", action="store_true", help="re-fetch companies already on file")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    rec = load()
    todo = universe()
    if a.syms:
        want = {s.strip() for s in a.syms.split(",") if s.strip()}
        todo = [t for t in todo if t[0] in want]
    if not a.force:
        todo = [t for t in todo if t[0] not in rec]
    print(f"{len(todo)} to classify ({len(rec)} on file)")
    if a.dry_run or not todo:
        print(" ".join(t[0] for t in todo[:200]) + (" ..." if len(todo) > 200 else ""))
        return 0
    today = dt.date.today().isoformat()
    last, got, miss = 0.0, 0, []

    def wait():
        nonlocal last
        gap = time.time() - last
        if gap < GAP:
            time.sleep(GAP - gap)
        last = time.time()

    warm = False
    try:
        for i, (sym, code, bse_only) in enumerate(todo, 1):
            vals = src = None
            if not bse_only:
                if not warm:  # NSE sets its session cookies on a page view before the API answers
                    wait()
                    _curl(NSE_HOME.format(sym=urllib.parse.quote(sym)), ["Accept: text/html"], cookies=True)
                    warm = True
                wait()
                c, body = _curl(NSE_API.format(sym=urllib.parse.quote(sym, safe="")), cookies=True, headers=[
                    "Accept: application/json, text/plain, */*",
                    f"Referer: {NSE_HOME.format(sym=urllib.parse.quote(sym))}"])
                if _refused(c, body):
                    raise Refused(f"NSE at {sym}: HTTP {c}, {body[:80]!r}")
                vals, src = nse_class(body), "NSE"
            if vals is None and code:
                wait()
                c, body = _curl(BSE_API.format(code=code), headers=[
                    "Accept: application/json, text/plain, */*",
                    "Referer: https://www.bseindia.com/", "Origin: https://www.bseindia.com"])
                if _refused(c, body):
                    raise Refused(f"BSE at {sym} ({code}): HTTP {c}, {body[:80]!r}")
                vals, src = bse_class(body), "BSE"
            if vals is None:
                miss.append(sym)
                continue
            rec[sym] = dict(zip(LEVELS, vals), src=src, d=today)
            got += 1
            if got % 25 == 0:
                save(rec)
                print(f"  {i}/{len(todo)}  {sym}: {' > '.join(vals)}")
    except Refused as e:
        if got:
            save(rec)
        print(f"stopped: {e}. {got} classified this run and saved; rerun later to continue.")
        return 2
    if got:
        save(rec)
    print(f"{got} classified ({len(rec)} on file)." + (f" No classification from either exchange for "
          f"{len(miss)}: {', '.join(miss[:30])}" if miss else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
