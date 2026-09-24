#!/usr/bin/env python3
"""Quarterly results (last 6 quarters) + balance-sheet equity, BVPS, ROE, DPS
for the NSE 100 (first) and the rest of the Nifty 500.

    python3 pipeline/results.py                 # nse100, then rest
    python3 pipeline/results.py --group nse100  # or rest / all
    python3 pipeline/results.py --syms TCS,INFY
    python3 pipeline/results.py --parse-only    # re-parse from cache, no network

Writes pipeline/inputs/results/<SYM>.json and cache/results_raw/results_report.json.

Three phases, shaped by NSE's two hosts (see memory nse-api-rate-limits):
  1. list   - www.nseindia.com/api/integrated-filing-results, ONE call at a
              time, >=1 s apart, content-validated; stops at the first block.
              Lists already cached by the alpha study (Aug-2026, with the
              Jun-26 quarter present) are reused instead of re-called.
  2. files  - the iXBRL filing tables on nsearchives.nseindia.com (never
              blocks), 10 parallel workers; alpha's cached copies are reused.
  3. parse  - pipeline/nseresults/extra.py (vendored alpha parser + BS/capital).

Values are as filed, normalised to Rs crore using each filing's declared
rounding (sanity-checked). Nothing is estimated; gaps stay null with a note.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from nseresults.extra import parse_filing, parse_xbrl  # noqa: E402
from nseresults.net import UA, utcnow              # noqa: E402

CACHE = ROOT / "cache" / "results_raw"
LISTS = CACHE / "lists"
MANIFEST = CACHE / "manifest.jsonl"
OUT = HERE / "inputs" / "results"
REPORT = CACHE / "results_report.json"
N500_URL = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"
NSE100_DIR = Path.home() / "Projects" / "nse100-holders" / "companies"
ALPHA_RAW = Path.home() / "Projects" / "alpha" / "data" / "raw"          # read-only
ALPHA_ACT = Path.home() / "Projects" / "alpha" / "data" / "actuals"      # read-only
CORP_ACT = Path.home() / "Projects" / "msci" / "data_dump" / "corporate_actions"
LIST_URL = "https://www.nseindia.com/api/integrated-filing-results?index=equities&symbol={sym}"
LIST_URL_FULL = LIST_URL + "&size=50"   # default page is 20 rows; revisions can push quarters off it
LIST_HDR = ["Accept: */*",
            "Referer: https://www.nseindia.com/companies-listing/corporate-filings-financial-results"]
N_QUARTERS = 6
# NSE carries no results for these: they are BSE-listed and only "permitted to
# trade" on NSE. api.bseindia.com answered Akamai 403 "Access Denied" to every
# request on 2026-09-25 (suggest, AnnSubCategoryGetData), so they stay open.
KNOWN_GAPS = {
    "ABBOTINDIA": "files results with BSE only (scrip 500488); api.bseindia.com refused (403) 2026-09-25",
    "BAYERCROP": "files results with BSE only (scrip 506285); api.bseindia.com refused (403) 2026-09-25",
    "MCX": "files results with BSE only (scrip 534091); api.bseindia.com refused (403) 2026-09-25",
    "DUMMYHEG": "Nifty 500 placeholder symbol (HEG demerger) - no filings exist",
}
TODAY = date.today()


class Blocked(Exception):
    pass


def _hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:24]


def _record(url, path, sha, source):
    with MANIFEST.open("a") as fh:
        fh.write(json.dumps({"url": url, "cached_as": str(path.relative_to(ROOT)),
                             "sha256": sha, "source": source,
                             "retrieved_at": utcnow()}) + "\n")


def _curl(url, headers=(), timeout=60):
    cmd = ["curl", "-sS", "-L", "-m", str(timeout), "-A", UA, "-w", "\n%{http_code}"]
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


# ------------------------------------------------------------------ universe

def universe():
    csvp = CACHE / "ind_nifty500list.csv"
    if not csvp.exists():
        code, body = _curl(N500_URL)
        if code != 200 or not body.startswith(b"Company Name"):
            raise SystemExit(f"Nifty 500 list download failed ({code})")
        csvp.write_bytes(body)
    n500 = [r["Symbol"].strip() for r in csv.DictReader(csvp.open())]
    nse100 = sorted(p.name for p in NSE100_DIR.iterdir() if p.is_dir())
    rest = [s for s in n500 if s not in set(nse100)]
    return nse100, rest, set(n500)


# ------------------------------------------------------------ phase 1: lists

def _valid_list(body: bytes):
    try:
        j = json.loads(body.decode("utf-8", "replace"))
    except Exception:
        return None
    if isinstance(j, dict) and isinstance(j.get("data"), list):
        return j
    return None


def _has_jun26(j):
    return any(r.get("qe_Date", "").upper() == "30-JUN-2026" and r.get("consolidated")
               for r in j.get("data", []))


def get_lists(syms, log, fresh_verify=()):
    """Sequential, content-validated. Returns {sym: list-json}."""
    LISTS.mkdir(parents=True, exist_ok=True)
    out, calls, last = {}, 0, 0.0
    for sym in syms:
        p = LISTS / f"{sym}.json"
        if p.exists() and sym not in fresh_verify:
            out[sym] = json.loads(p.read_text())
            continue
        url = LIST_URL.format(sym=urllib.parse.quote(sym, safe=""))
        ap = ALPHA_RAW / f"{_hash(url)}.json"
        if ap.exists() and sym not in fresh_verify:
            j = _valid_list(ap.read_bytes())
            complete = j and (j.get("totalCount") or 0) <= len(j.get("data", [])) \
                or (j and len(select(j)[1]) >= N_QUARTERS)
            if j and _has_jun26(j) and complete:
                p.write_text(json.dumps(j))
                _record(url, p, hashlib.sha256(ap.read_bytes()).hexdigest(),
                        "alpha cache (retrieved 2026-08-30)")
                out[sym] = j
                continue
        gap = time.time() - last
        if gap < 1.1:
            time.sleep(1.1 - gap)
        last = time.time()
        code, body = _curl(LIST_URL_FULL.format(sym=urllib.parse.quote(sym, safe="")),
                           LIST_HDR, timeout=30)
        calls += 1
        j = _valid_list(body)
        if code in (401, 403) or (j is None and (b"Access Denied" in body or b"<HTML" in body.upper()[:200])):
            log(f"  BLOCKED at {sym}: HTTP {code}, body {body[:80]!r}")
            raise Blocked(sym)
        if j is None:
            log(f"  list {sym}: HTTP {code}, not JSON ({body[:60]!r}) - skipped")
            continue
        p.write_text(json.dumps(j))
        _record(url, p, hashlib.sha256(body).hexdigest(), "www.nseindia.com")
        out[sym] = j
    return out, calls


# ------------------------------------------------------ select filings

def _qe(s):
    for f in ("%d-%b-%Y", "%d-%B-%Y"):
        try:
            return datetime.strptime(s.strip().title(), f).date()
        except (ValueError, AttributeError):
            pass
    return None


def _bdt(s):
    try:
        return datetime.strptime((s or "").strip().title(), "%d-%b-%Y %H:%M:%S")
    except ValueError:
        return datetime.min


def _filed(r):
    """Revised filings carry revised_Date and a null broadcast_Date."""
    return max(_bdt(r.get("broadcast_Date")), _bdt(r.get("revised_Date")))


def doc_url(r):
    """The rendered iXBRL table if NSE has one, else the raw XBRL instance."""
    u = (r.get("ixbrl") or "").strip()
    return u if u and not u.endswith("/-") else (r.get("xbrl") or "").strip()


def select(j):
    """(scope, [(qe, scope, row)]) - latest filing per (qe, scope), last 6 qe."""
    best = {}
    for r in j.get("data", []):
        sc = (r.get("consolidated") or "").strip()
        url = doc_url(r)
        qe = _qe(r.get("qe_Date") or "")
        if url.endswith("/-") or url.endswith("/null"):
            url = ""
        if sc not in ("Consolidated", "Standalone") or not url or not qe:
            continue
        if "GOVERNANCE" in url.upper():
            continue
        k = (qe, sc)
        if k not in best or _filed(r) > _filed(best[k]):
            best[k] = r
    qes = sorted({k[0] for k in best}, reverse=True)[:N_QUARTERS]
    if not qes:
        return None, []
    scope = "Consolidated" if (qes[0], "Consolidated") in best else "Standalone"
    other = "Standalone" if scope == "Consolidated" else "Consolidated"
    picks = []
    for q in sorted(qes):
        if (q, scope) in best:
            picks.append((q, scope, best[(q, scope)]))
        elif (q, other) in best:
            picks.append((q, other, best[(q, other)]))
    return scope, picks


# ------------------------------------------------------ phase 2: files

def _file_path(url):
    return CACHE / f"{_hash(url)}.bin"


def _ok_html(b: bytes):
    if b"Access Denied" in b[:2000] or len(b) < 3000:
        return False
    head = b[:400].lower()
    if b"<?xml" in head or b"xbrl" in head:
        return b"contextref" in b[:400000].lower()
    return b"<t" in b[:200000].lower()


def fetch_file(url):
    p = _file_path(url)
    if p.exists() and _ok_html(p.read_bytes()):
        return "cache"
    ap = ALPHA_RAW / p.name
    if ap.exists() and _ok_html(ap.read_bytes()):
        shutil.copyfile(ap, p)
        _record(url, p, hashlib.sha256(p.read_bytes()).hexdigest(), "alpha cache copy")
        return "alpha"
    for attempt in range(3):
        code, body = _curl(url, ["Referer: https://www.nseindia.com/"], timeout=90)
        if code == 200 and _ok_html(body):
            p.write_bytes(body)
            _record(url, p, hashlib.sha256(body).hexdigest(), "nsearchives")
            return "net"
        time.sleep(1.5 * (attempt + 1))
    return f"fail:{code}"


def fetch_files(urls, workers, log):
    urls = sorted(set(urls))
    stats = {}
    with ThreadPoolExecutor(workers) as ex:
        for u, st in zip(urls, ex.map(fetch_file, urls)):
            stats[u] = st
    fails = {u: s for u, s in stats.items() if s.startswith("fail")}
    log(f"  files: {len(urls)} total; "
        f"cache {sum(s == 'cache' for s in stats.values())}, "
        f"alpha {sum(s == 'alpha' for s in stats.values())}, "
        f"net {sum(s == 'net' for s in stats.values())}, fail {len(fails)}")
    return fails


# ------------------------------------------------------ corporate actions

_MON = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _d(s):
    try:
        return datetime.strptime(s.strip(), "%d-%b-%Y").date()
    except (ValueError, AttributeError):
        return None


_FV = None


def nse_face_value(sym):
    """Face value from NSE's securities list (nsearchives EQUITY_L.csv)."""
    global _FV
    if _FV is None:
        _FV = {}
        p = CACHE / "EQUITY_L.csv"
        if not p.exists():
            code, body = _curl("https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv")
            if code == 200 and body.startswith(b"SYMBOL"):
                p.write_bytes(body)
        if p.exists():
            for r in csv.DictReader(p.open()):
                r = {k.strip(): (v or "").strip() for k, v in r.items()}
                try:
                    _FV[r["SYMBOL"]] = float(r["FACE VALUE"])
                except (KeyError, ValueError):
                    pass
    return _FV.get(sym)


def corp_actions(sym):
    p = CORP_ACT / f"{sym}.json"
    if not p.exists():
        fv = nse_face_value(sym)
        return {"divs": [], "events": [], "face_value": fv, "empty": True} if fv else None
    divs, events = [], []   # events: (exdate, factor>1 means more shares)
    rows = json.loads(p.read_text())
    for r in rows:
        s = (r.get("subject") or "").lower()
        ex = _d(r.get("exDate") or "")
        if not ex:
            continue
        m = re.search(r"\bbonus\s+(\d+)\s*:\s*(\d+)", s)
        if m and "ncrps" not in s and "preference" not in s:
            a, b = int(m.group(1)), int(m.group(2))
            events.append((ex, (a + b) / b, r["subject"].strip(), "bonus"))
            continue
        m = re.search(r"from\s+r[se]\.?\s*([\d.]+).*?to\s+r[se]\.?\s*([\d.]+)", s)
        if m and ("split" in s or "sub-division" in s or "consolidation" in s):
            events.append((ex, float(m.group(1)) / float(m.group(2)), r["subject"].strip(), "split"))
            continue
        if "div" in s:
            amts = re.findall(r"r[se]\.?\s*(?:per\s*)?(\d+(?:\.\d+)?)", s)
            if not amts:
                amts = re.findall(r"dividend\s*-\s*(\d+(?:\.\d+)?)", s)
            amt = sum(float(a) for a in amts)
            if amt:
                divs.append((ex, amt, r["subject"].strip(), (r.get("faceVal") or "").strip()))
    fv = max(rows, key=lambda r: _d(r.get("exDate") or "") or date.min).get("faceVal") if rows else None
    try:
        fv = float(fv)
    except (TypeError, ValueError):
        fv = nse_face_value(sym)
    return {"divs": divs, "events": events, "face_value": fv, "empty": not rows}


def adj_factor(events, after, upto=None):
    """Share-count multiplier for events with ex-date > after (and <= upto)."""
    f = 1.0
    for ex, fac, *_ in events:
        if ex > after and (upto is None or ex <= upto):
            f *= fac
    return f


def fv_at(ca, d):
    """Face value in force on date d: current NSE face value x later splits."""
    try:
        fv = float(ca["face_value"])
    except (TypeError, ValueError, KeyError):
        return None
    for ex, fac, _, kind in ca["events"]:
        if kind == "split" and ex > d:
            fv *= fac
    return fv


def _pdate(s):
    for f in ("%d-%m-%Y", "%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime((s or "").strip().title(), f).date()
        except ValueError:
            pass
    return None


# ------------------------------------------------------ phase 3: build

def qlabel(qe: date):
    q = {6: 1, 9: 2, 12: 3, 3: 4}.get(qe.month)
    fy = qe.year + 1 if qe.month >= 4 else qe.year
    return f"Q{q} FY{str(fy)[-2:]}", qe.strftime("%b-%y")


def _r(x, n=2):
    return None if x is None else round(x, n)


def build(sym, lj, alpha_rows, log):
    scope, picks = select(lj)
    notes, flags = [], []
    if not picks:
        return None, ["no integrated-filing financial results in NSE list"]
    parsed = []
    for qe, sc, row in picks:
        url = doc_url(row)
        p = _file_path(url)
        if not p.exists():
            flags.append(f"{qe}: filing not downloaded")
            continue
        html = p.read_text(encoding="utf-8", errors="ignore")
        try:
            f = parse_xbrl(html, url, qe.isoformat()) if url.lower().endswith(".xml") \
                else parse_filing(html, url, sc)
        except Exception as exc:        # keep going, report
            flags.append(f"{qe}: parse error {exc}")
            continue
        f["qe"], f["scope_used"], f["url"], f["row"] = qe, sc, url, row
        if f.get("basis") == "XBRL":
            notes.append(f"{qlabel(qe)[0]}: NSE has no iXBRL table for this filing - read from the XBRL instance")
        parsed.append(f)
    if not parsed:
        return None, flags or ["no filings parsed"]
    fmt = parsed[-1]["format"]
    bank, ins = parsed[-1]["bank"], parsed[-1]["insurer"]
    rev_basis = ("interest earned (bank)" if bank else
                 "net premium (insurer: net premium income / net premium written)" if ins else
                 "revenue from operations")
    ca = corp_actions(sym)
    events = ca["events"] if ca else []

    # ---- per-quarter values ------------------------------------------------
    quarters = []
    for f in parsed:
        qe = f["qe"]
        ql, dl = qlabel(qe)
        if bank:
            rev = f.get("interest_earned_cr")
        elif ins:
            rev = f.get("net_premium_cr")
        else:
            rev = f.get("revenue_ops_cr")
        if rev is None and not bank and not ins and f.get("revenue_cr") is not None:
            rev = f.get("revenue_cr")
            notes.append(f"{ql}: revenue from operations not found - total income used")
        pat = f.get("pat_cr")
        po = f.get("pat_owners_cr")
        if po == 0 and pat and abs(pat) > 0.5:
            po = None        # a blank owners row renders as 0.00 in some filings
        po_missing = po is None and pat is not None
        if po_missing and (f["scope_used"] == "Standalone" or ins):
            po, po_missing = pat, False     # no minority interest in a standalone statement
        # period covered by the quarter column
        st = _pdate(f.get("start"))
        qstart = date(qe.year if qe.month > 3 else qe.year, qe.month - 2, 1)
        if st and st != qstart:
            rec_period = f"{ql}: filing's quarter column states period {st} to {qe}"
        else:
            rec_period = None
        ytd_start = st if st and st.month == 4 and st.day == 1 and qe.month in (9, 12, 3) \
            and st.year == (qe.year if qe.month > 3 else qe.year - 1) else None
        # face value in force at quarter end (NSE corporate actions), filing's as fallback
        fv_f = f.get("face_value")
        fv_q = fv_at(ca, qe) if ca and ca.get("face_value") else None
        filed_on = _filed(f["row"]).date() if _filed(f["row"]) != datetime.min else None
        if fv_q is None:
            fv_q = fv_f
        elif fv_f and abs(fv_f - fv_q) > 1e-9:
            fv_post = fv_at(ca, filed_on) if filed_on else None
            if not (fv_post and abs(fv_f - fv_post) < 1e-9):
                notes.append(f"{ql}: filing states face value {fv_f:g}; NSE face value "
                             f"Rs {fv_q:g} used for the share count")
        shares = f["paidup_cr"] * 1e7 / fv_q if f.get("paidup_cr") and fv_q else None
        rec = {"q": ql, "d": dl, "end": qe.isoformat(), "rev": _r(rev), "pat": _r(pat),
               "pat_owners": _r(po), "eps": f.get("eps_basic"), "src": f["url"]}
        if f["scope_used"] != scope:
            rec["scope"] = f["scope_used"]
            notes.append(f"{ql}: {scope} filing absent - {f['scope_used']} used")
        rec["_shares"], rec["_nci"], rec["_filed_on"] = shares, f.get("nci_cr"), filed_on
        rec["_po_missing"] = po_missing
        rec["_period"] = rec_period
        rec["_ytd_start"] = ytd_start
        quarters.append(rec)
        if f["scale_note"]:
            # Declared lakhs/crores but the table carries whole rupees (common in
            # Q4 FY25-Q1 FY26 filings): a note, not a flag. Anything else: flag.
            (notes if "factor 1e-07" in f["scale_note"] else flags).append(
                f"{ql} units: {f['scale_note']}")
        if not f["rounding"]:
            flags.append(f"{ql} units: filing declares no rounding level")
        for k in ("rev", "pat", "eps"):
            if rec[k] is None:
                flags.append(f"{ql}: {k} missing")

    # ---- period check: a mis-typed start date vs YTD figures in the quarter column
    revs = sorted(r["rev"] for r in quarters if r["rev"])
    for i, r in enumerate(quarters):
        if r["_period"]:
            med = revs[len(revs) // 2] if revs else None
            prior = [q for q in quarters[:i] if r["_ytd_start"] and
                     date.fromisoformat(q["end"]) > r["_ytd_start"] and not q["_period"]]
            n_prior = {9: 1, 12: 2, 3: 3}.get(date.fromisoformat(r["end"]).month, 0)
            if r["rev"] and med and 0.6 <= r["rev"] / med <= 1.6:
                notes.append(r["_period"] + " - revenue is quarter-sized, treated as a date typo")
            elif r["_ytd_start"] and len(prior) == n_prior:
                filed = {k: r[k] for k in ("rev", "pat", "pat_owners", "eps")}
                for k in ("rev", "pat", "pat_owners", "eps"):
                    if r[k] is not None and all(q[k] is not None for q in prior):
                        r[k] = _r(r[k] - sum(q[k] for q in prior))
                    else:
                        r[k] = None
                if r["_nci"] is not None and all(q["_nci"] is not None for q in prior):
                    r["_nci"] = r["_nci"] - sum(q["_nci"] for q in prior)
                r["derived"] = f"year-to-date {r['_ytd_start']}..{r['end']} as filed minus prior quarters"
                r["ytd_filed"] = filed
                notes.append(r["_period"] + f" (year-to-date); quarter derived as YTD minus "
                             f"{', '.join(q['q'] for q in prior)} (EPS by subtraction is approximate)")
                r["_period"] = None
            else:
                flags.append(r["_period"] + " - may hold year-to-date figures")


    # ---- share count sanity: gross outliers vs the other quarters ---------
    # Some filings put the paid-up capital in the wrong unit or swap it with the
    # face value (BAJAJFINSV Q1 FY27, LTM Q4 FY26). Bring every quarter to the
    # current share basis; a quarter off the median by >1.5x takes the median.
    base = [(r, r["_shares"] * adj_factor(events, date.fromisoformat(r["end"])))
            for r in quarters if r["_shares"]]
    if len(base) >= 3:
        med = sorted(v for _, v in base)[len(base) // 2]
        vals = [v for _, v in base]
        for i, (r, v) in enumerate(base):
            ratio = v / med
            lg = abs(math.log10(ratio))
            unit_slip = lg >= 0.97 and abs(lg - round(lg)) < 0.03          # x10, x100 ...
            extreme = ratio > 5 or ratio < 0.2
            isolated = (0 < i < len(base) - 1 and
                        all(abs(math.log(v / n)) > math.log(1.5) for n in (vals[i - 1], vals[i + 1])) and
                        abs(math.log(vals[i - 1] / vals[i + 1])) < math.log(1.1))
            if unit_slip or extreme or isolated:
                fixed = med / adj_factor(events, date.fromisoformat(r["end"]))
                notes.append(f"{r['q']}: filing's paid-up capital / face value gives "
                             f"{r['_shares']:,.0f} shares, inconsistent with the other quarters; "
                             f"{fixed:,.0f} used (median, corporate-action adjusted)")
                r["_shares"] = fixed

    # ---- gate: EPS x shares ~ pat_owners (and owners-line repair) ---------
    gate_eps = []
    for rec in quarters:
        sh, eps, po, pat, nci = rec["_shares"], rec["eps"], rec["pat_owners"], rec["pat"], rec["_nci"]
        if not sh or eps in (None, 0) or (po is None and not rec["_po_missing"]):
            if rec["_po_missing"]:
                rec["pat_owners"] = pat
                notes.append(f"{rec['q']}: owners-of-parent line blank; PAT used (no EPS check possible)")
            gate_eps.append((rec["q"], None))
            continue
        qe = date.fromisoformat(rec["end"])
        post = adj_factor(events, qe, rec["_filed_on"]) if rec["_filed_on"] else 1.0
        esh = sh * post                    # EPS denominator basis on the filing date
        if post != 1.0 and po:             # not every filer restates EPS for a post-period split
            if abs(eps * sh / 1e7 - po) < abs(eps * esh / 1e7 - po):
                esh, post = sh, 1.0
        implied = eps * esh / 1e7          # Rs cr
        tol = max(0.05 * abs(implied), 0.0051 * esh / 1e7)   # 5%, or EPS 2-dp rounding

        def ok(x):
            return x is not None and abs(x - implied) <= tol
        if post != 1.0:
            notes.append(f"{rec['q']}: EPS is on the post-bonus/split basis (x{post:g} "
                         "between quarter end and filing)")
        if rec["_po_missing"]:
            cand = pat - nci if nci is not None else pat
            if nci is not None and nci != 0 or abs(cand - implied) <= 0.15 * abs(implied):
                rec["pat_owners"] = po = _r(cand)
                notes.append(f"{rec['q']}: owners-of-parent line blank; "
                             f"{'PAT - NCI (both as filed)' if nci is not None else 'PAT'} = {cand:,.2f} used"
                             f"{' (EPS-consistent)' if ok(cand) else ' (within 15% of EPS x shares; see EPS gate)'}")
            else:
                notes.append(f"{rec['q']}: owners-of-parent line blank in filing and PAT {pat} is >15% from "
                             f"EPS x shares ({implied:,.1f}) - minority interest likely; pat_owners left null")
                gate_eps.append((rec["q"], None))
                continue
        if not ok(po):
            fixed = None
            for name, v in (("PAT - non-controlling interest", None if pat is None or nci is None else pat - nci),
                            ("the non-controlling-interest line (owners/NCI lines swapped in the filing)", nci)):
                if v is not None and ok(v):
                    fixed = (name, v)
                    break
            sum_ok = (pat is not None and nci is not None and
                      abs(po + nci - pat) <= 0.01 * abs(pat) + 0.5)
            if not fixed and pat is not None and nci is not None and not sum_ok \
                    and abs(pat - nci - implied) <= 0.10 * abs(implied):
                fixed = ("PAT - non-controlling interest (filed owners + NCI != PAT; within 10% of "
                         "EPS x period-end shares)", pat - nci)
            if fixed:
                notes.append(f"{rec['q']}: filed owners-of-parent PAT {po} fails the EPS check "
                             f"(EPS x shares = {implied:,.1f}); {fixed[0]} = {fixed[1]:,.2f} used")
                rec["pat_owners_filed"] = po
                rec["pat_owners"] = po = _r(fixed[1])
        dev = implied / po - 1 if po else None
        gate_eps.append((rec["q"], dev))
        if not ok(po):
            why = ""
            if implied * (po or 0) < 0:
                why = " (sign differs)"
            elif pat and ok(pat):
                why = " (EPS matches total PAT)"
            flags.append(f"{rec['q']} EPS gate: EPS {eps} x {esh/1e7:,.3f} cr sh = "
                         f"{implied:,.1f} vs pat_owners {po} "
                         f"({'n/a' if dev is None else f'{dev:+.1%}'}){why}; implied EPS "
                         f"denominator {po * 1e7 / eps / 1e7:,.3f} cr sh" if po else
                         f"{rec['q']} EPS gate: EPS {eps} but pat_owners {po}")

    for r in quarters:
        if r["eps"] == 0 and r["pat_owners"] and abs(r["pat_owners"]) > 1:
            flags.append(f"{r['q']}: filing reports EPS 0 with pat_owners {r['pat_owners']} - "
                         "EPS set to null (not reported)")
            r["eps"] = None

    # ---- gate: revenue QoQ jump and share-count jumps --------------------
    for a, b in zip(quarters, quarters[1:]):
        if a["rev"] and b["rev"] and a["rev"] > 0 and b["rev"] > 0:
            r = b["rev"] / a["rev"]
            if r > 3 or r < 1 / 3:
                flags.append(f"{b['q']} revenue jump x{r:.2f} QoQ ({a['rev']} -> {b['rev']})")
        if a["_shares"] and b["_shares"]:
            r = b["_shares"] / a["_shares"]
            if r > 1.25 or r < 0.8:
                fac = adj_factor(events, date.fromisoformat(a["end"]), date.fromisoformat(b["end"]))
                if abs(fac / r - 1) < 0.03:
                    notes.append(f"{b['q']}: share count x{r:.2f} vs prior quarter = corporate action x{fac:g}")
                else:
                    notes.append(f"{b['q']}: share count x{r:.2f} vs prior quarter (issue/buyback/merger)")

    # ---- balance sheet ----------------------------------------------------
    bss = [(f["qe"], f["bs"], f) for f in parsed if f.get("bs")]
    bvps = equity = bs_date = roe = None
    roe_basis = shares_basis = None
    if bss:
        qe_bs, bs, fbs = bss[-1]
        equity = bs["equity_cr"]
        bs_date = qe_bs.isoformat()
        rq = next((r for r in quarters if r["end"] == bs_date), None)
        sh_bs = rq["_shares"] if rq else None
        if sh_bs:
            post = adj_factor(events, qe_bs)
            bvps = equity * 1e7 / (sh_bs * post)
            fvb = (fv_at(ca, qe_bs) if ca else None) or fbs.get("face_value")
            shares_basis = (f"{sh_bs * post:,.0f} shares: paid-up equity capital / face value "
                            f"Rs {fvb if fvb is None else f'{fvb:g}'} at {bs_date} "
                            f"(capital per filing; face value per NSE corporate actions)")
            if post != 1.0:
                shares_basis += f", x{post:g} for bonus/split after that date (current basis)"
                notes.append(f"BVPS on current share basis (x{post:g} bonus/split after {bs_date})")
            if fvb and bs.get("capital_cr"):
                sh_cap = bs["capital_cr"] * 1e7 / fvb
                if abs(sh_cap / sh_bs - 1) > 0.02:
                    notes.append(f"balance-sheet equity share capital implies {sh_cap:,.0f} shares vs "
                                 f"{sh_bs:,.0f} from the results page (treasury shares / unit slip)")
        if ins:
            notes.append("equity = share capital + reserves & surplus (excl. fair-value change account)")
        if bank:
            notes.append("equity = capital + reserves & surplus (bank format; excl. minority interest)")
        # ROE: TTM PAT to owners / avg of the last two half-yearly equity figures
        ttm = quarters[-4:]
        if len(ttm) == 4 and all(q["pat_owners"] is not None for q in ttm) and len(bss) >= 2:
            eq2 = [b[1]["equity_cr"] for b in bss[-2:]]
            avg = sum(eq2) / 2
            if avg > 0:
                roe = sum(q["pat_owners"] for q in ttm) / avg * 100
                roe_basis = (f"TTM PAT to owners {ttm[0]['q']}-{ttm[-1]['q']} / avg equity to owners "
                             f"({bss[-2][0].strftime('%b-%y')}, {bss[-1][0].strftime('%b-%y')})")
        elif len(ttm) == 4 and len(bss) == 1:
            roe = sum(q["pat_owners"] or 0 for q in ttm) / equity * 100 if equity > 0 else None
            roe_basis = f"TTM PAT to owners / closing equity {bs_date} (one balance sheet only)"
    else:
        flags.append("no statement of assets & liabilities parsed - BVPS/ROE null")

    # ---- DPS (TTM, bonus/split-adjusted to current basis) ----------------
    dps, dps_note = None, None
    if ca is None:
        dps_note = "no corporate-actions file"
    else:
        start = TODAY - timedelta(days=365)
        rows = [(ex, amt, subj) for ex, amt, subj, _ in ca["divs"] if start < ex <= TODAY]
        dps = 0.0
        adj = []
        for ex, amt, subj in rows:
            fac = adj_factor(ca["events"], ex)
            dps += amt / fac
            if fac != 1.0:
                adj.append(f"{subj} ({ex}) / {fac:g}")
        dps = round(dps, 4)
        dps_note = (f"{len(rows)} dividend(s) with ex-date {start} to {TODAY} (NSE corporate "
                    f"actions, file of 2026-09-20)" +
                    (f"; bonus/split-adjusted to current shares: {'; '.join(adj)}" if adj
                     else "; no bonus/split after these ex-dates"))
        if ca.get("empty"):
            dps_note = "NSE corporate-actions list has no records for this symbol (file of 2026-09-20)"

    last = quarters[-1]
    out = {"sym": sym, "scope": scope, "format": fmt, "rev_basis": rev_basis,
           "quarters": [{k: v for k, v in q.items() if not k.startswith("_")} for q in quarters[-N_QUARTERS:]],
           "bvps": _r(bvps), "equity_cr": _r(equity), "bs_date": bs_date,
           "roe": _r(roe), "roe_basis": roe_basis,
           "dps_ttm": dps, "dps_basis": dps_note,
           "shares_basis": shares_basis,
           "notes": sorted(set(notes)), "flags": [x for x in flags if x],
           "generated": utcnow()}
    for q, rq in zip(out["quarters"], quarters):
        q["shares"] = round(rq["_shares"]) if rq["_shares"] else None

    # ---- compare with alpha's parsed rows (same filing) ------------------
    cmp_ = []
    if alpha_rows:
        by = {(r["period_end"], r["scope"]): r for r in alpha_rows}
        for q in quarters:
            a = by.get((q["end"], q.get("scope", scope)))
            if not a:
                continue
            arev = a["interest_earned_cr"] if bank else a["revenue_ops_cr"]
            for k, av in (("rev", arev), ("pat", a["pat_cr"]),
                          ("pat_owners", a["pat_owners_cr"]), ("eps", a["eps_basic"])):
                mv = q[k]
                if av is None or mv is None:
                    if av is not None and mv is None:
                        cmp_.append(f"{q['q']} {k}: alpha {av} vs ours None")
                    continue
                if abs(mv - av) > max(0.011, abs(av) * 1e-4):
                    if k == "pat_owners" and a["pat_owners_cr"] is None:
                        continue
                    cmp_.append(f"{q['q']} {k}: alpha {av} vs ours {mv}")
    return out, {"flags": flags, "alpha_diff": cmp_, "gate_eps": gate_eps}


# ------------------------------------------------- Ind AS 117 supplement

MANUAL_117 = HERE / "nseresults" / "manual_indas117.json"


def indas117_block(sym):
    """Q1 FY27 figures filed only as a PDF under Ind AS 117 (STARHEALTH, NIVABUPA).

    Kept OUT of the IGAAP-format quarter series on purpose: the bases differ
    (e.g. NIVABUPA Q4 FY26 PAT is 345.13 cr IGAAP vs 159.36 cr Ind AS 117).
    Values are the filed Rs-lakh figures, transcribed from the PDF table images
    (pipeline/nseresults/manual_indas117.json), gate-checked here.
    """
    if not MANUAL_117.exists():
        return None, []
    m = json.loads(MANUAL_117.read_text()).get(sym)
    if not m:
        return None, []
    flags, qs = [], []
    for i, per in enumerate(m["periods"]):
        cr = lambda k: None if m[k][i] is None else round(m[k][i] / 100, 2)   # lakhs -> crore
        shares = m["share_capital"][i] * 1e5 / m["face_value"]
        rec = {"period": per, "insurance_revenue": cr("insurance_revenue"), "pbt": cr("pbt"),
               "pat": cr("pat"), "pat_owners": cr("pat"), "eps": m["eps_basic"][i],
               "eps_diluted": m["eps_diluted"][i], "gwp": cr("gwp"),
               "total_equity_cr": cr("total_equity"), "shares": round(shares)}
        if per != "FY26":
            d = date.fromisoformat(per)
            rec["q"], rec["d"] = qlabel(d)
        implied = rec["eps"] * shares / 1e7
        if rec["pat"] and abs(implied - rec["pat"]) > max(0.05 * abs(rec["pat"]), 0.0051 * shares / 1e7):
            flags.append(f"Ind AS 117 {per}: EPS {rec['eps']} x {shares / 1e7:.3f} cr sh = {implied:.1f} "
                         f"vs PAT {rec['pat']}")
        qs.append(rec)
    latest = qs[0]
    block = {"basis": ("Ind AS 117 (IRDAI circular IRDAI/F&I/CIR/MISC/92/7/2026, 8-Jul-2026); "
                       "filed only as a PDF - no XBRL on NSE; transcribed from the table images; "
                       "NOT comparable with the IGAAP-format quarters in `quarters`"),
             "src": m["src"], "pages": m["pages"], "announced": m["announced"], "scope": m["scope"],
             "rev_basis": "insurance revenue (Ind AS 117)",
             "latest": latest, "comparatives": qs[1:],
             "bvps_2026_06_30": round(latest["total_equity_cr"] * 1e7 / latest["shares"], 2),
             "flags": flags}
    return block, flags


# ------------------------------------------------------------ cross-check

def crosscheck(n, seed, log):
    """Print n random companies' latest quarter next to the filing's own rows."""
    from nseresults.financials import _table_rows, _row_label
    files = sorted(OUT.glob("*.json"))
    rnd = random.Random(seed)
    for p in rnd.sample(files, min(n, len(files))):
        d = json.loads(p.read_text())
        q = d["quarters"][-1]
        html = _file_path(q["src"]).read_text(encoding="utf-8", errors="ignore")
        log(f"--- {d['sym']} {q['q']} ({d['scope']}, {d['format']}) {q['src']}")
        log(f"    ours: rev {q['rev']} | pat {q['pat']} | pat_owners {q['pat_owners']} | "
            f"eps {q['eps']} | shares {q.get('shares')}")
        want = re.compile(r"level of rounding|^(total )?revenue from operations$|^total interest earned|"
                          r"^net premium (income|written)$|^total profit .*period$|"
                          r"^net profit .*(period|after tax)|attributable to owners of parent$|"
                          r"after taxes?,? minority|^profit\s*/?\s*\(?\s*loss\s*\)?\s*after tax|"
                          r"^basic (earnings|eps)|^basic$|^paid[- ]?up equity|^face value|"
                          r"^date of end of reporting period|^nature of report")
        shown = 0
        for c in _table_rows(html):
            li, lab = _row_label(c)
            if lab and want.search(lab):
                log("      " + " | ".join(x[:55] for x in c[li:li + 3]))
                shown += 1
            if shown > 16:
                break


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", choices=["nse100", "rest", "all"], default="all")
    ap.add_argument("--syms")
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--parse-only", action="store_true")
    ap.add_argument("--crosscheck", type=int, default=0, help="print N random companies vs filing")
    ap.add_argument("--seed", type=int, default=20260925)
    ap.add_argument("--verify-fresh", default="TATACHEM,INFY",
                    help="alpha-cached symbols to re-list fresh from NSE as a check")
    a = ap.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    logf = (CACHE / "results_run.log").open("a")

    def log(m):
        print(m, flush=True)
        logf.write(m + "\n")
        logf.flush()

    if a.crosscheck:
        crosscheck(a.crosscheck, a.seed, log)
        return
    nse100, rest, n500 = universe()
    groups = []
    if a.syms:
        groups = [("custom", a.syms.split(","))]
    else:
        if a.group in ("nse100", "all"):
            groups.append(("nse100", nse100))
        if a.group in ("rest", "all"):
            groups.append(("rest", rest))
    report = json.loads(REPORT.read_text()) if REPORT.exists() else {}
    t0 = time.time()
    blocked = False
    for gname, syms in groups:
        tg = time.time()
        log(f"== {gname}: {len(syms)} symbols  ({datetime.now():%H:%M:%S})")
        lists = {}
        if a.parse_only:
            lists = {s: json.loads((LISTS / f"{s}.json").read_text())
                     for s in syms if (LISTS / f"{s}.json").exists()}
        else:
            try:
                fresh = [s for s in a.verify_fresh.split(",") if s in syms]
                lists, calls = get_lists(syms, log, fresh_verify=fresh)
                log(f"  phase 1 lists: {len(lists)}/{len(syms)} ({calls} live NSE calls, "
                    f"{time.time() - tg:.0f}s)")
            except Blocked as b:
                blocked = True
                lists = {s: json.loads((LISTS / f"{s}.json").read_text())
                         for s in syms if (LISTS / f"{s}.json").exists()}
                log(f"  STOPPED phase 1 at {b} - continuing with {len(lists)} lists already held")
            t1 = time.time()
            urls = [doc_url(r) for s, j in lists.items() for _, _, r in select(j)[1]]
            fails = fetch_files(urls, a.workers, log)
            log(f"  phase 2 files: {time.time() - t1:.0f}s")
        t2 = time.time()
        done, failed = [], {}
        for s in syms:
            if s not in lists:
                failed[s] = "no NSE list (blocked or not JSON)"
                continue
            ap_ = ALPHA_ACT / f"{s}.json"
            arows = json.loads(ap_.read_text()) if ap_.exists() else None
            try:
                res, info = build(s, lists[s], arows, log)
            except Exception as exc:
                failed[s] = f"build error: {exc!r}"
                continue
            if res is None:
                failed[s] = KNOWN_GAPS.get(s) or "; ".join(info)
                continue
            ia, ia_flags = indas117_block(s)
            if ia:
                res["ind_as117"] = ia
                res["notes"].append(f"{ia['latest']['q']} filed only under Ind AS 117 (PDF): see "
                                    "`ind_as117`; `quarters` stays on the IGAAP-format series")
                info["flags"] = info["flags"] + ia_flags
            (OUT / f"{s}.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
            done.append(s)
            report.setdefault("companies", {})[s] = {"group": gname, **info,
                                                     "n_quarters": len(res["quarters"]),
                                                     "latest": res["quarters"][-1]["q"]}
        log(f"  phase 3 parse: {len(done)} written, {len(failed)} failed ({time.time() - t2:.0f}s)")
        report.setdefault("groups", {})[gname] = {
            "n": len(syms), "done": len(done), "failed": failed,
            "wall_s": round(time.time() - tg), "at": utcnow()}
        for s, why in failed.items():
            log(f"    FAIL {s}: {why}")
        if blocked:
            break
    REPORT.write_text(json.dumps(report, indent=1, default=str))
    log(f"== total wall {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
