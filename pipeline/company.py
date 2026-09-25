"""Per-company data layer: src/co/<SYM>.json, src/univ.json, pipeline/inputs/px_universe.json.

    python3 pipeline/company.py ANANDRATHI RELIANCE      # named companies
    python3 pipeline/company.py --nse100                 # the NSE 100 runs (+ ANANDRATHI)
    python3 pipeline/company.py --nifty500               # every Nifty 500 name with a run
    python3 pipeline/company.py --univ-only              # rebuild src/univ.json + px_universe.json

Every number is computed from local data (nothing is refetched):
  holders   holdermap run.json (Bloomberg-backed NSE 100 runs, or filing-mode Nifty 500 runs)
  trend     SEBI shareholding XBRL, six quarter-end filings Mar-25..Jun-26, share COUNTS
            (never the filed %, never NumberOfVotingRights), members matched by
            CategoryOfShareholdersAxis case-insensitively with the Goverment/Government alias
  prices    NSE bhavcopy (msci/data_dump/bhavcopy.db), EQ row (BE/BZ when EQ is absent),
            followed across NSE symbol changes; bonus/split adjusted by dividing pre-ex-date
            prices by the ratio. Ratios come from three sources (NSE CA API dump, fundamentals.db,
            freefloat's merged API+PR-archive events); every ex-date is snapped to the day the
            price actually moved (+-7 trading days). Any adjusted day-on-day move >25% that no
            corporate action explains fails the company (the file is NOT written) or, when it
            lies before the 3-year window, withholds only the since-listing anchor.

Per-company curation that used to be hand-typed in data.py (display names, stale Bloomberg rows,
HUF notes) lives in pipeline/inputs/overrides/<SYM>.json.
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import glob
import io
import json
import math
import os
import re
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME = Path.home() / "Projects"
INP = ROOT / "pipeline" / "inputs"
OUT_CO = ROOT / "src" / "co"
OUT_UNIV = ROOT / "src" / "univ.json"
OUT_PXU = INP / "px_universe.json"
OVR = INP / "overrides"
RESULTS = INP / "results"
REPORT = ROOT / "cache" / "company_report.json"

BHAV_DB = HOME / "msci" / "data_dump" / "bhavcopy.db"
FUND_DB = HOME / "msci" / "data_dump" / "fundamentals.db"
MSCI_CA = HOME / "msci" / "data_dump" / "corporate_actions"
MSCI_XBRL = HOME / "msci" / "data_dump" / "xbrl"
HM_XBRL = HOME / "holdermap" / "data" / "cache" / "xbrl"
FF = HOME / "exports" / "freefloat" / "data"
FF_XBRL, FF_SHP = FF / "xbrl_raw", FF / "shp"
FF_CA = FF / "ca_company.json"
SYMCHG = ROOT / "cache" / "symbolchange.csv"          # nsearchives copy, 24-Sep-2026
if not SYMCHG.exists():
    SYMCHG = FF / "symbolchange.csv"
BSE_SCRIPS = HOME / "msci" / "data_dump" / "bse_scrips.json"
REG_FOREIGN = HOME / "holdermap" / "data" / "registry" / "foreign.yaml"
NSE100_RUNS = HOME / "nse100-holders" / "companies"
NSE500_RUNS = HOME / "nse500-runs"
N500_CSV = [INP / "ind_nifty500list.csv", NSE500_RUNS / "ind_nifty500list.csv",
            ROOT / "cache" / "results_raw" / "ind_nifty500list.csv"]
PR_ZIP = ROOT / "cache" / "pr" / "PR230926.zip"   # NSE PR archive: issue size + mcap on END
NTM_CSV = INP / "ind_niftytotalmarket_list.csv"   # names / industry for names outside the Nifty 500
EQ_MASTER = HOME / "msci" / "data_dump" / "nse_equity_master.csv"
IDX_CHANGES = HOME / "netra" / "data" / "nifty_index_changes.csv"   # NSE Indices press releases
EXTRA_RUNS = INP / "extra"                                         # <SYM>/run.json for non-index extras

END = "2026-09-23"                                # last close in the snapshot
FIL = ["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"]
QL = ["Mar-25", "Jun-25", "Sep-25", "Dec-25", "Mar-26", "Jun-26"]
PERIODS = ["Q2/2025", "Q3/2025", "Q4/2025", "Q1/2026", "Q2/2026", "Q3/2026"]
HQ = ["Jun-25", "Sep-25", "Dec-25", "Mar-26", "Jun-26", "Sep-26"]
PEND = {"Q2/2025": "2025-06-30", "Q3/2025": "2025-09-30", "Q4/2025": "2025-12-31",
        "Q1/2026": "2026-03-31", "Q2/2026": "2026-06-30", "Q3/2026": "2026-09-30"}
ANCHORS = ["2023-09-22", "2025-09-23", "2025-12-31", "2026-03-24", "2026-06-23", "2026-08-21", END]
MAX_JUMP = 0.25

FOREIGN = {"Foreign AMC", "Foreign Government", "Foreign Insurance", "Foreign corporate", "Bank"}
DOM = {"Domestic AMC", "Domestic Insurance", "Domestic Pension Fund", "Government"}
SUB = {"Foreign AMC": "Asset manager", "Foreign Government": "Central bank", "Foreign Insurance": "Insurer",
       "Foreign corporate": "Holding co.", "Bank": "Bank group", "Domestic AMC": "Mutual fund",
       "Domestic Insurance": "Life insurer", "Promoter": "Promoter group", "Individual": "Public",
       "Domestic corporate": "Corporate"}
ORG = re.compile(r"\b(ltd|limited|pvt|private|llp|trust|foundation|inc|corp|corporation|company|co|"
                 r"holdings?|investments?|enterprises?|ventures?|capital|finance|financial|fund|"
                 r"bank|partners|lp|plc|sa|ag|gmbh|bv|nv|ab|as|society|association|estate|huf|"
                 r"family|group|industries|international|services|management|securities|"
                 r"trustee|trustees|advisors?|properties|infra\w*)\b", re.I)


def D(s): return dt.date.fromisoformat(s)


def iso(d): return d.isoformat()


class Fail(Exception):
    pass


def write_atomic(path, text):
    """Readers (the site build, the lead's poller) never see a half-written file."""
    tmp = Path(path).parent / ("." + Path(path).name + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


# --------------------------------------------------------------------------------------------
# reference data
# --------------------------------------------------------------------------------------------
def index_list(p):
    if not p.exists():
        return {}
    rows = list(csv.DictReader(open(p, encoding="utf-8-sig")))
    return {r["Symbol"].strip(): dict(n=r["Company Name"].strip(), ind=r["Industry"].strip(),
                                       isin=r["ISIN Code"].strip()) for r in rows}


def n500_changes():
    """Scheduled Nifty 500 changes after END: ({entrant: effective date}, {leaver: effective date})."""
    add, drop = {}, {}
    if IDX_CHANGES.exists():
        for r in csv.DictReader(open(IDX_CHANGES, encoding="utf-8")):
            if r.get("index_name") == "Nifty 500" and (r.get("effective_date") or "") > END:
                (add if r.get("action") == "ADD" else drop if r.get("action") == "DROP" else {})[r["symbol"].strip()] = r["effective_date"]
    return add, drop


def nifty500():
    for p in N500_CSV:
        if p.exists():
            rows = list(csv.DictReader(open(p, encoding="utf-8-sig")))
            return {r["Symbol"].strip(): dict(n=r["Company Name"].strip(), ind=r["Industry"].strip(),
                                               isin=r["ISIN Code"].strip()) for r in rows}
    return {}


def nse100():
    return sorted(p.name for p in NSE100_RUNS.iterdir() if (p / "run.json").exists())


def bse_codes():
    try:
        return {r["ISIN_NUMBER"]: r["SCRIP_CD"] for r in json.load(open(BSE_SCRIPS)) if r.get("ISIN_NUMBER")}
    except Exception:
        return {}


def foreign_registry():
    """bloomberg_name/alias -> country, from holdermap's foreign.yaml (no yaml module needed)."""
    out, cur, names = {}, None, []
    if not REG_FOREIGN.exists():
        return out
    for line in open(REG_FOREIGN, encoding="utf-8"):
        m = re.match(r"^- bloomberg_name:\s*(.+?)\s*$", line)
        if m:
            names = [m.group(1).strip("'\"")]
            continue
        m = re.match(r"^\s+country:\s*(\S+)", line)
        if m and names:
            for n in names:
                out[n] = m.group(1).strip("'\"")
    return out


def symbol_history():
    """new symbol -> [(old symbol, change date)] from NSE's symbolchange.csv."""
    h = collections.defaultdict(list)
    if SYMCHG.exists():
        for r in csv.reader(open(SYMCHG, encoding="utf-8", errors="replace")):
            if len(r) < 4:
                continue
            try:
                d = dt.datetime.strptime(r[3].strip(), "%d-%b-%Y").date()
            except ValueError:
                continue
            h[r[2].strip()].append((r[1].strip(), d))
    return h


# --------------------------------------------------------------------------------------------
# shareholding XBRL
# --------------------------------------------------------------------------------------------
_SHP_IDX = {}


def _ok_xml(p):
    try:
        ET.parse(p)
        return True
    except ET.ParseError:
        return False


def xbrl_path(sym, fdate, alts=()):
    for p in xbrl_paths(sym, fdate, alts):
        if _ok_xml(p):
            return p
    return None


def _dparse(x):
    try:
        return dt.datetime.strptime((x or "").strip()[:11], "%d-%b-%Y")
    except ValueError:
        return dt.datetime(2000, 1, 1)


def _ff_cands(sym, fdate, alts=()):
    """NSE-index filings for fdate, newest (submission or revision) first: [(revised, path)]."""
    want = D(fdate).strftime("%d-%b-%Y").upper()
    out = []
    for s in (sym, *alts):
        f = FF_SHP / f"{s}.json"
        if not f.exists():
            continue
        if s not in _SHP_IDX:
            _SHP_IDX[s] = json.load(open(f))
        for e in _SHP_IDX[s]:
            if (e.get("date") or "").upper() != want or not e.get("xbrl"):
                continue
            p = FF_XBRL / e["xbrl"].rsplit("/", 1)[-1]
            if p.exists() and p.stat().st_size > 1000:
                rev = (e.get("revisedData") or "").lower() == "revised" or bool(e.get("revisionDate"))
                out.append((max(_dparse(e.get("submissionDate")), _dparse(e.get("revisionDate"))), rev, p))
    out.sort(key=lambda x: x[0], reverse=True)
    return [(rev, p) for _, rev, p in out]


def xbrl_paths(sym, fdate, alts=()):
    ff = _ff_cands(sym, fdate, alts)
    # a revision NSE published after the original wins over our cached copies of the original
    # (VIJAYA Jun-26: revised 07-Sep-2026, total 102,896,728 not 102,988,473 -> promoter 52.51%, NSE's figure)
    if ff and ff[0][0]:
        yield ff[0][1]
    for s in (sym, *alts):
        for p in (HM_XBRL / s / f"{fdate}.xml", MSCI_XBRL / s / f"{fdate}.xml", FF / "bse" / "backfill" / f"{s}_{fdate}.xml"):
            if p.exists() and p.stat().st_size > 1000:
                yield p
    for rev, p in ff:
        yield p


def parse_shp(path):
    """member(lower) -> (NumberOfShares, NumberOfShareholders) for single-dim category contexts."""
    root = ET.parse(path).getroot()
    ctx, meta = {}, {}
    for el in root:
        tag = el.tag.split("}")[-1]
        if tag == "context":
            dims = [(m.get("dimension", "").split(":")[-1], (m.text or "").split(":")[-1].strip())
                    for m in el.iter() if m.tag.endswith("explicitMember")]
            ctx[el.get("id")] = dims
    vals = collections.defaultdict(dict)
    for el in root:
        tag = el.tag.split("}")[-1]
        cid = el.get("contextRef")
        if not cid:
            continue
        dims = ctx.get(cid, [])
        if not dims:
            if tag in ("Symbol", "ISIN", "ScripCode", "NameOfTheCompany", "DateOfReport") and el.text:
                meta.setdefault(tag, el.text.strip())
            continue
        if len(dims) != 1 or dims[0][0] != "CategoryOfShareholdersAxis":
            continue
        if tag in ("NumberOfShares", "NumberOfShareholders", "NumberOfSharesUnderlyingOutstandingDepositoryReceipts"):
            try:
                vals[dims[0][1].lower()].setdefault(tag, int(round(float(el.text))))
            except (TypeError, ValueError):
                pass
    return vals, meta


def _g(vals, *members, key="NumberOfShares"):
    for m in members:
        v = vals.get(m.lower() + "member") if not m.lower().endswith("member") else vals.get(m.lower())
        if v and key in v:
            return v[key]
    return 0


def filing_row(vals):
    """Category share counts of one filing, with depository receipts (DRs) kept out of every category.

    SEBI's filed % is shares / (A+B+C2). Issuers file the DR custodian in one of two places:
      style 1  C1 'shares underlying DRs' (Non-Promoter-Non-Public), outside A+B: RELIANCE, INFY, SBIN,
               HDFCBANK, INDUSINDBK. The filed denominator already excludes them.
      style 2  inside the public table: the current format's Institutions (Foreign) row 'Overseas
               Depositories (holding DRs) (balancing figure)' (OverseasDepositoriesMember: WIPRO, DRREDDY,
               ICICIBANK from Jun-26), or, in the older layout with no C1, under Non-institutions (ICICIBANK
               to Mar-26: the public table's 'shares underlying DRs' column). Filed FII then jumps with the
               format change (ICICIBANK 34.49% -> 49.82%).
    Rule for every quarter: dr = C1 + depository shares inside the public table; den = tot - dr; fii
    excludes depositories; oth = den - prom - fii - dii - ind, so prom+fii+dii+ind+oth = den and
    den + dr = tot. 'filed' keeps the percentages exactly as filed (shares / (tot - C1))."""
    g = lambda *m: _g(vals, *m)
    gd = lambda *m: _g(vals, *m, key="NumberOfSharesUnderlyingOutstandingDepositoryReceipts")
    tot = g("ShareholdingPattern")
    nh = _g(vals, "ShareholdingPattern", key="NumberOfShareholders")
    prom = g("ShareholdingOfPromoterAndPromoterGroup")
    pub = g("PublicShareholding")
    npnp = g("SharesHeldByNonPromoterNonPublicShareholders")
    c1 = g("CustodianOrDRHolder")
    c2 = g("EmployeeBenefitsTrusts")
    odm = g("OverseasDepositories")                  # style 2, current format: inside Institutions (Foreign)
    old = gd("PublicShareholding") if (not c1 and not odm) else 0   # style 2, older layout (no C1)
    dep = odm + old
    fii_f, dii = g("InstitutionsForeign"), g("InstitutionsDomestic")
    fii = fii_f - odm
    iS = g("ResidentIndividualShareholdersHoldingNominalShareCapitalUpToRsTwoLakh")
    iL = g("ResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh")
    dr = c1 + dep
    den = tot - dr
    r = dict(tot=tot, nh=nh, prom=prom, fii=fii, dii=dii, ind=iS + iL,
             mf=g("MutualFundsOrUTI"), ins=g("InsuranceCompanies"),
             f1=g("InstitutionsForeignPortfolioInvestorCategoryOne", "InstitutionsForeignPortfolioInvestorCatergoryOne"),
             f2=g("InstitutionsForeignPortfolioInvestorCategoryTwo", "InstitutionsForeignPortfolioInvestorCatergoryTwo"),
             aif=g("AlternativeInvestmentFunds"), iS=iS, iL=iL, bc=g("BodiesCorporate"), nri=g("NonResidentIndians"),
             govt=g("Goverments", "Governments"), fcos=g("ForeignCompanies"),
             fdi=g("ForeignDirectInvestment"),            # strategic foreign holders filed INSIDE Institutions (Foreign)
             dr=dr, den=den, dr_in_public=dep > 0, c2=c2)
    r["oth"] = den - prom - fii - dii - r["ind"]
    fden = (tot - c1) or 1                           # the filed denominator, A+B+C2
    r["filed"] = {k: round(100 * v / fden, 4) for k, v in
                  dict(prom=prom, fii=fii_f, dii=dii, mf=r["mf"], ins=r["ins"], pub=pub).items()}
    r["_pub"], r["_npnp"], r["_c1"], r["_dep"] = pub, npnp, c1, dep
    r["_fii_filed"], r["_dii_filed"], r["_mf_filed"] = fii_f, dii, r["mf"]
    return r


# --------------------------------------------------------------------------------------------
# prices + corporate actions
# --------------------------------------------------------------------------------------------
SER_PRI = {"EQ": 0, "BE": 1, "BZ": 2}


def price_rows(con, sym, symhist):
    """[(date, o, h, l, c, series, symbol)] across renames; EQ preferred per date."""
    spans = [(sym, None, None)]
    seen, frontier, lo = {sym}, [(sym, None)], {}
    while frontier:
        s, upto = frontier.pop()
        for old, d in symhist.get(s, []):
            if old in seen or (upto and d > upto):
                continue
            seen.add(old)
            spans.append((old, None, d))
            lo[s] = max(lo.get(s, d), d) if s in lo else d
            frontier.append((old, d))
    # the current symbol's rows before its (latest) rename belong to whoever used it before
    spans = [(s, lo.get(s), hi) for s, _, hi in spans]
    best = {}
    for s, frm, upto in spans:
        q = "select trade_date,open,high,low,close,series from bhav where symbol=? and trade_date<=?"
        for d, o, h, l, c, ser in con.execute(q, (s, END)):
            if ser not in SER_PRI or c is None or c <= 0:
                continue
            if frm and d < iso(frm):
                continue
            if upto and d >= iso(upto):
                continue
            k = (SER_PRI[ser], 0 if s == sym else 1)
            if d not in best or k < best[d][0]:
                best[d] = (k, (d, o or c, h or c, l or c, c, ser, s))
    return [best[d][1] for d in sorted(best)], [s for s, _, _ in spans]


_RATIO_BONUS = re.compile(r"\bbon(?:us)?\b\D{0,20}?(\d+)\s*:\s*(\d+)", re.I)     # 'Bonus 1:1', 'Bon 5:1'
_RATIO_FVSPL = re.compile(r"f\.?v\.?\s*spl\w*\W*r[se]\.?\s*([\d.]+)\s*/?-?\s*to\s*r[se]\.?\s*([\d.]+)", re.I)  # 'Fv Spl-Rs10tors2'
_RIGHTS = re.compile(r"rights\s*(\d+)\s*:\s*(\d+)\s*@\s*(premium\s*(?:of\s*)?|par\b|discount\s*(?:of\s*)?)?"
                     r"\s*(?:rs\.?|re\.?|inr)?\s*([\d.]+)?", re.I)
_DIVIDEND = re.compile(r"(?:dividend|\bdiv\b)[^/]*?(?:rs\.?|re\.?|inr)\s*([\d.]+)", re.I)
_RATIO_SPLIT = re.compile(r"(?:split|sub-?division|consolidat)\D*?(?:from\s*)?(?:rs\.?|re\.?|inr)?\s*([\d.]+)\s*/?-?\s*"
                          r"(?:per\s*share\s*)?(?:each\s*)?to\s*(?:rs\.?|re\.?|inr)?\s*([\d.]+)", re.I)


def _pref(subj):
    """Bonus preference shares (NCRPS) never touch the equity share count."""
    s = (subj or "").lower()
    return "ncrps" in s or "preference" in s or "debenture" in s


def parse_subject(subj):
    """NSE CA subject -> [(kind, share multiplier)]."""
    out = []
    s = subj or ""
    for a, b in _RATIO_BONUS.findall(s):
        a, b = int(a), int(b)
        if a > 0 and b > 0 and not _pref(s) and "dvr" not in s.lower():
            out.append(("bonus", (a + b) / b))
    for a, b in _RATIO_SPLIT.findall(s) + _RATIO_FVSPL.findall(s):
        try:
            a, b = float(a), float(b)
        except ValueError:
            continue
        if a > 0 and b > 0 and a != b:
            out.append(("split", a / b))
    return out


def ca_events(symbols, isins, ffca):
    raw, text = [], []
    for s in symbols:
        f = MSCI_CA / f"{s}.json"
        if f.exists():
            for x in json.load(open(f)):
                try:
                    d = dt.datetime.strptime(x.get("exDate", ""), "%d-%b-%Y").date()
                except ValueError:
                    continue
                subj = x.get("subject") or ""
                try:
                    fv = float(x.get("faceVal") or 0) or None
                except ValueError:
                    fv = None
                text.append((d, subj, fv))
                for kind, r in parse_subject(subj):
                    raw.append((d, r, kind, "nse-ca"))
    try:
        con = sqlite3.connect(f"file:{FUND_DB}?mode=ro", uri=True)
        for s in symbols:
            for d, kind, fac, subj in con.execute(
                    "select ex_date,kind,factor,subject from corporate_actions where symbol=? and kind in ('split','bonus')", (s,)):
                if not _pref(subj):
                    raw.append((D(d), float(fac), kind, "fundamentals"))
        con.close()
    except sqlite3.Error:
        pass
    comps = {ffca["company_of"].get(i) for i in isins if i} - {None}
    for c in comps:
        for d, r, kind, src, *rest in ffca["events"].get(c, []):
            if not _pref(rest[0] if rest else ""):
                raw.append((D(d), float(r), kind, "freefloat-" + src))
    # merge: same ratio (1%) within 10 days is one event
    ev = []
    for d, r, kind, src in sorted(raw):
        if r <= 0 or abs(r - 1) < 1e-9:
            continue
        for e in ev:
            if e["kind"] == kind and abs(math.log(e["r"] / r)) < 0.01 and abs((e["d"] - d).days) <= 10:
                e["src"].add(src)
                break
        else:
            ev.append(dict(d=d, r=r, kind=kind, src={src}))
    # a split and a bonus on the same day compound (x10 split + x2 bonus = x20): kept as two events
    return ev, text


def snap_and_adjust(rows, events, sym, manual=(), catext=(), infer_before=""):
    """Snap each event to the actual price move, adjust, and scan for unexplained jumps."""
    dates = [r[0] for r in rows]
    close = [r[4] for r in rows]
    idx = {d: i for i, d in enumerate(dates)}
    applied, notes = [], []
    first, last = dates[0], dates[-1]
    opn = [r[1] for r in rows]
    evs = [e for e in events if first < iso(e["d"]) <= last]   # before the first traded day / after END: skip
    clusters = []
    for e in sorted(evs, key=lambda e: e["d"]):
        if clusters and (e["d"] - clusters[-1][-1]["d"]).days <= 7:
            clusters[-1].append(e)
        else:
            clusters.append([e])

    def match(ed, r):
        """Trading day within +-7 of ed where the close-to-close OR close-to-open move equals ratio r."""
        j = next((i for i, d in enumerate(dates) if d >= ed), None)
        if j is None:
            return None
        tol = min(0.10, 0.35 * abs(math.log(r)))
        best = None
        for k in range(max(1, j - 7), min(len(dates), j + 8)):
            err = min(abs(math.log(close[k - 1] / close[k]) - math.log(r)),
                      abs(math.log(close[k - 1] / opn[k]) - math.log(r)) if opn[k] else 9)
            if err < tol and (best is None or (err, abs(k - j)) < (best[0], abs(best[1] - j))):
                best = (err, k)
        return best and best[1]

    for ci, cl in enumerate(clusters):
        ed = iso(cl[0]["d"])
        prod = math.prod(e["r"] for e in cl)
        k = match(ed, prod) if len(cl) > 1 else None
        todo = [(cl, k)] if k is not None else [([e], match(iso(e["d"]), e["r"])) for e in cl]
        seen = set()
        for grp, k in todo:
            for e in grp:
                desc = f"{e['kind']} x{e['r']:g} ex {iso(e['d'])} ({'/'.join(sorted(e['src']))})"
                if k is None:
                    if 0.75 < e["r"] < 4 / 3:
                        # a 1:10 bonus moves the price 9%, inside ordinary noise; the exchange's record stands
                        k = next((i for i, d in enumerate(dates) if d >= iso(e["d"])), None)
                        notes.append(f"{sym}: {desc} has no clear price move (small ratio); applied on the "
                                     f"source ex-date {dates[k]}")
                    else:
                        notes.append(f"{sym}: {desc} has no matching price move within 7 trading days; NOT applied")
                        continue
                if len(todo) > 1:
                    # matched one by one: two records of one ratio on one day are one action filed
                    # under two labels (their product did not match the price move)
                    key = (k, round(math.log(e["r"]), 3))
                    if key in seen:
                        notes.append(f"{sym}: {desc} duplicates another record on {dates[k]}; applied once")
                        continue
                    seen.add(key)
                if dates[k] != iso(e["d"]):
                    notes.append(f"{sym}: {desc} ex-date snapped -> {dates[k]}")
                applied.append(dict(d=dates[k], r=e["r"], kind=e["kind"], src=sorted(e["src"]), snapped=True, cl=ci))
    for m in manual:                        # overrides: verified factors (e.g. demerger), applied as given
        applied.append(dict(d=m[0], r=float(m[1]), kind=m[2] if len(m) > 2 else "manual", src=["override"],
                            snapped=True, cl=-1))
    # the same event reported >10 days apart by two sources snaps onto one day: keep it once
    # (events from ONE cluster are distinct actions, e.g. split x2 + bonus x2 on the same day)
    uniq = {}
    for a in applied:
        key = (a["d"], round(math.log(a["r"]), 3))
        if key in uniq and uniq[key][0] != a["cl"]:
            notes.append(f"{sym}: x{a['r']:g} on {a['d']} reported twice (source dates differ); applied once")
            continue
        uniq.setdefault(key, (a["cl"], []))[1].append(a)
    applied = sorted((a for _, L in uniq.values() for a in L), key=lambda a: a["d"])
    S, jumps = _adjust(rows, applied, idx)
    # Demergers: NSE's special pre-open session re-prices the parent on the ex-date. Adjust every earlier
    # price by prev close / ex-day open (raw, same share basis), whenever a demerger / scheme of
    # arrangement is on record within 10 days of the gap. Anything still unexplained fails below.
    dm = []
    for jp in jumps:
        if jp.get("gap"):
            continue
        k = idx[jp["d"]]
        near = [t.strip() for d, t, *_ in catext if abs((d - D(jp["d"])).days) <= 10
                and re.search(r"demerg|arrangement", t, re.I)]
        if near and opn[k]:
            r = round(close[k - 1] / opn[k], 6)
            dm.append(dict(d=jp["d"], r=r, kind="demerger", src=["prev close/ex-day open"], snapped=True, cl=-3))
            notes.append(f"{sym}: demerger ex {jp['d']} ({'; '.join(near)}): prices before adjusted by "
                         f"{close[k - 1]}/{opn[k]} = {r:g}")
    if dm:
        applied = sorted(applied + dm, key=lambda a: a["d"])
        S, jumps = _adjust(rows, applied, idx)
    # Rights issues and extraordinary dividends on record within 10 days of a still-unexplained gap:
    # adjust earlier prices by the standard price-only factor - rights: prev close / TERP, where
    # TERP = (b x prev close + a x issue price) / (a + b) for 'Rights a:b @ premium X' (issue = face
    # value + X); dividend: prev close / (prev close - D) when D >= 10% of the price (NSE's own threshold
    # for adjusting derivatives). Applied only when the factor brings that day's move within 25%.
    rd = []
    for jp in jumps:
        if jp.get("gap"):
            continue
        k = idx[jp["d"]]
        P, mv = close[k - 1], jp["move"] / 100
        best = None
        for d, t, *fv in catext:
            if abs((d - D(jp["d"])).days) > 10:
                continue
            fv = fv[0] if fv else None
            f = kind = None
            m = _RIGHTS.search(t)
            if m and fv:
                a, b = int(m.group(1)), int(m.group(2))
                how, val = (m.group(3) or "").lower(), float(m.group(4)) if m.group(4) else None
                issue = (fv + val if how.startswith("premium") and val is not None else
                         fv - val if how.startswith("discount") and val is not None else
                         fv if how.startswith("par") else val)
                if a > 0 and b > 0 and issue and issue > 0 and issue < P and "partly" not in t.lower():
                    f, kind = P / ((b * P + a * issue) / (a + b)), "rights"
            elif re.search(r"dividend|\bdiv\b", t, re.I):
                dv = sum(float(x) for x in _DIVIDEND.findall(t) if x.replace(".", "", 1).isdigit())
                if 0.10 * P <= dv < P:
                    f, kind = P / (P - dv), "dividend"
            if f and f > 1 and abs((1 + mv) * f - 1) <= MAX_JUMP:
                cand = (abs((1 + mv) * f - 1), f, kind, t.strip())
                best = min(best, cand) if best else cand
        if best:
            rd.append(dict(d=jp["d"], r=round(best[1], 6), kind=best[2], src=["CA record: " + best[3]], snapped=True, cl=-4))
            notes.append(f"{sym}: {best[2]} ex {jp['d']} ({best[3]}): prices before adjusted by {best[1]:.6g} "
                         f"({jp['move']:+.1f}% -> {100 * ((1 + mv) * best[1] - 1):+.1f}%)")
    if rd:
        applied = sorted(applied + rd, key=lambda a: a["d"])
        S, jumps = _adjust(rows, applied, idx)
    # Before the 3-year window only: a gap that never trades back through intraday and whose close or
    # open equals a standard bonus/split ratio within 5.5% (the ex-date often closes on a 5% circuit:
    # NMDC 2008-04-10 prev close / close = 9.5238 = 10 / 1.05) is a share-count action missing from the
    # CA records (they thin out before ~2010). It is applied, labelled 'inferred', so the since-listing
    # base stays usable. Inside the window nothing is inferred: an unexplained gap there fails the company.
    inf = []
    for jp in jumps:
        if jp["d"] >= infer_before or jp.get("gap"):
            continue
        k = idx[jp["d"]]
        if any(re.search(r"demerg|arrangement|amalgam|capital reduction", t, re.I)
               for d, t, *_ in catext if abs((d - D(jp["d"])).days) <= 10):
            continue
        obs = [close[k - 1] / close[k]] + ([close[k - 1] / opn[k]] if opn[k] else [])
        err, r = min((min(abs(math.log(o / r)) for o in obs), r) for r in CANON)
        if err < INFER_TOL:
            inf.append(dict(d=jp["d"], r=r, kind="inferred", src=["price-gap"], snapped=True, cl=-2))
            notes.append(f"{sym}: x{r:g} on {jp['d']} inferred from a non-traded price gap "
                         f"({jp['move']:+.1f}%, no CA record); pre-window, since-listing base only")
    if inf:
        applied = sorted(applied + inf, key=lambda a: a["d"])
        S, jumps = _adjust(rows, applied, idx)
    return S, applied, notes, jumps


# only ratios whose gap (>=50%) no ordinary event mimics: 1:1 bonus/2-for-1 split, 3:2 bonus, 2:1 bonus,
# 3:1 bonus, 5/10/20-for-1 splits, and their consolidation inverses. 1:2 or 1:3 bonuses (-33%/-25%) look
# like demergers and are never inferred.
CANON = [2.0, 2.5, 3.0, 4.0, 5.0, 10.0, 20.0, 0.5, 0.2, 0.1]
INFER_TOL = math.log(1.055)
PRICE_ONLY = {"demerger", "rights", "dividend"}      # adjust prices, never share counts


def _adjust(rows, applied, idx):
    """Cumulative factor (divide prices before each ex-date by its ratio) + the >25% jump scan."""
    fac = [1.0] * len(rows)          # price factor: every event
    sfac = [1.0] * len(rows)         # share factor: share-count events only (never demergers)
    for a in applied:
        k = idx[a["d"]]
        for i in range(k):
            fac[i] *= a["r"]
            if a["kind"] not in PRICE_ONLY:
                sfac[i] *= a["r"]
    S = [dict(d=r[0], o=r[1] / f, h=r[2] / f, l=r[3] / f, c=r[4] / f, raw=r[4], f=f, sf=sf, ser=r[5], sym=r[6])
         for r, f, sf in zip(rows, fac, sfac)]
    jumps = []
    for i in range(1, len(S)):
        m = S[i]["c"] / S[i - 1]["c"] - 1
        if abs(m) > MAX_JUMP:
            P, x = S[i - 1]["c"], S[i]
            if (D(x["d"]) - D(S[i - 1]["d"])).days > 10:
                # the stock did not trade in between (e.g. FORCEMOT Oct-2023..Feb-2024: absent from NSE's
                # own bhavcopy too) - a move across a trading gap, reported, not failed
                jumps.append(dict(d=x["d"], prev=S[i - 1]["d"], move=round(100 * m, 1),
                                  raw=[S[i - 1]["raw"], x["raw"]], sym=x["sym"], gap=True))
                continue
            # the day traded at least a quarter of the way back toward the previous close -> a market
            # move (IEX 24-Jul-2025, ZEEL 23-Jan-2024), not a missed corporate action: on an ex-date the
            # whole session trades at the new level
            if (m < 0 and x["h"] >= x["c"] + 0.25 * (P - x["c"])) or (m > 0 and x["l"] <= x["c"] - 0.25 * (x["c"] - P)):
                continue
            jumps.append(dict(d=S[i]["d"], prev=S[i - 1]["d"], move=round(100 * m, 1),
                              raw=[S[i - 1]["raw"], S[i]["raw"]], sym=S[i]["sym"]))
    return S, jumps


# --------------------------------------------------------------------------------------------
# the company build
# --------------------------------------------------------------------------------------------
def load_run(sym):
    for p in (NSE100_RUNS / sym / "run.json", NSE500_RUNS / sym / "run.json", EXTRA_RUNS / sym / "run.json"):
        if p.exists():
            return json.load(open(p)), p
    if sym == "ANANDRATHI" and (INP / "run.json").exists():
        return json.load(open(INP / "run.json")), INP / "run.json"
    return None, None


def load_override(sym):
    p = OVR / f"{sym}.json"
    return json.load(open(p)) if p.exists() else {}


def generic_name(h):
    n = h.strip()
    if n.endswith("/The"):
        n = "The " + n[:-4]
    n = re.sub(r"/India$", "", n)
    if n.isupper() and len(n) > 4:
        keep = {"LIC", "SBI", "HDFC", "ICICI", "UTI", "IDFC", "HSBC", "UBS", "BNP", "DSP", "PPFAS", "LLP", "HUF",
                "FPI", "AIF", "PMS", "AMC", "II", "III", "IV", "USA", "US", "UK", "NPS", "EPFO", "ESOP", "BNY", "KKR"}
        n = " ".join(w if w in keep else w.capitalize() for w in n.split())
    return n


class Ctx:
    """Reference data loaded once per process."""

    def __init__(self):
        self.n500 = nifty500()
        self.ntm = index_list(NTM_CSV)                     # Nifty Total Market (750): names/industry fallback
        self.n500_add, self.n500_drop = n500_changes()
        self.master = {}
        if EQ_MASTER.exists():
            for r in csv.DictReader(open(EQ_MASTER, encoding="utf-8-sig")):
                r = {k.strip(): (v or "").strip() for k, v in r.items()}
                self.master[r.get("SYMBOL")] = dict(n=r.get("NAME OF COMPANY"), isin=r.get("ISIN NUMBER"))
        self.bse = bse_codes()
        self.reg = foreign_registry()
        self.symhist = symbol_history()
        self.ffca = json.load(open(FF_CA)) if FF_CA.exists() else {"company_of": {}, "events": {}}
        self.con = sqlite3.connect(f"file:{BHAV_DB}?mode=ro", uri=True)
        self.bench = None
        dj = ROOT / "src" / "data.json"
        if dj.exists():
            self.bench = json.load(open(dj)).get("bench")
        self.nse_mcap = {}
        if PR_ZIP.exists():
            z = zipfile.ZipFile(PR_ZIP)
            name = next(n for n in z.namelist() if n.lower().startswith("mcap"))
            rd = csv.reader(io.TextIOWrapper(z.open(name), encoding="latin-1"))
            next(rd)
            for r in rd:
                if len(r) >= 10 and r[2].strip() in ("EQ", "BE", "BZ"):
                    try:
                        self.nse_mcap[r[1].strip()] = (int(float(r[7])), float(r[8]), float(r[9]))
                    except ValueError:
                        pass


def ref(ctx, sym):
    """Name / industry / ISIN from the Nifty 500 list, else Nifty Total Market, else NSE's equity master."""
    return ctx.n500.get(sym) or ctx.ntm.get(sym) or dict(ctx.master.get(sym) or {}, ind="")


def membership(ctx, sym):
    """idx = index membership as of END (the Nifty 500 list before the 30-Sep-2026 change), plus the
    scheduled change dates; extra = a company outside the index that the dashboard carries anyway."""
    m = dict(idx=["n500"] if sym in ctx.n500 else [])
    if sym in ctx.n500_add:
        m["n500_from"] = ctx.n500_add[sym]
    if sym in ctx.n500_drop:
        m["n500_to"] = ctx.n500_drop[sym]
    m["extra"] = not m["idx"] and "n500_from" not in m
    return m


def filings(sym, alts=()):
    out, meta, miss = [], {}, []
    for fd, ql in zip(FIL, QL):
        p = xbrl_path(sym, fd, alts)
        if not p:
            miss.append(fd)
            out.append(None)
            continue
        vals, m = parse_shp(p)
        meta = m or meta
        r = filing_row(vals)
        r["q"], r["fd"], r["src"] = ql, fd, str(p)
        out.append(r)
    return out, meta, miss


def latest_filing(sym, alts=()):
    """The most recent parseable, checksum-clean shareholding filing on or before END - quarter-end or
    not (e.g. TORNTPHARM 2026-07-20 after its merger allotment, ADANIENT 2026-07-07)."""
    dates = set()
    for s in (sym, *alts):
        for base in (HM_XBRL / s, MSCI_XBRL / s):
            if base.is_dir():
                dates |= {f.stem for f in base.glob("*.xml") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", f.stem)}
        fi = FF_SHP / f"{s}.json"
        if fi.exists():
            if s not in _SHP_IDX:
                _SHP_IDX[s] = json.load(open(fi))
            for e in _SHP_IDX[s]:
                try:
                    dates.add(dt.datetime.strptime(e.get("date") or "", "%d-%b-%Y").date().isoformat())
                except ValueError:
                    pass
    for d in sorted((d for d in dates if d <= END), reverse=True):
        p = xbrl_path(sym, d, alts)
        if not p:
            continue
        r = filing_row(parse_shp(p)[0])
        if r["tot"] > 0 and r["prom"] + r["_pub"] + r["_npnp"] == r["tot"] and r["oth"] >= 0:
            r["fd"], r["src"] = d, str(p)
            return r
    return None


def idx_of(S, d):
    """Index of trading day d in S (exact match)."""
    lo, hi = 0, len(S) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if S[mid]["d"] < d:
            lo = mid + 1
        else:
            hi = mid
    if S[lo]["d"] != d:
        raise KeyError(d)
    return lo


def on_or_before(S, d):
    lo, hi = 0, len(S) - 1
    if not S or S[0]["d"] > d:
        return None
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if S[mid]["d"] <= d:
            lo = mid
        else:
            hi = mid - 1
    return S[lo]


def prices_for(ctx, sym, isins, manual=()):
    rows, syms = price_rows(ctx.con, sym, ctx.symhist)
    if not rows:
        ser = {r[0] for r in ctx.con.execute("select distinct series from bhav where symbol=?", (sym,))}
        if ser & {"RR", "IV"}:
            raise Fail(f"REIT/InvIT (series {'/'.join(sorted(ser))}): unitholding pattern, not supported yet")
        raise Fail(f"no bhavcopy rows for {sym}")
    if rows[-1][0] != END:
        raise Fail(f"last bhavcopy close is {rows[-1][0]}, not {END}")
    isins = set(isins) | {r[0] for r in ctx.con.execute(
        "select distinct isin from bhav where symbol=? and trade_date>='2021-01-01' and isin is not null", (sym,))}
    events, text = ca_events(syms, isins, ctx.ffca)
    w3lo = iso(dt.date(D(END).year - 3, D(END).month, D(END).day) - dt.timedelta(days=10))
    S, applied, notes, jumps = snap_and_adjust(rows, events, sym, manual, text, w3lo)
    after = [dict(d=iso(e["d"]), r=e["r"]) for e in events if iso(e["d"]) > END]
    return S, applied, notes, jumps, syms, text, after


def build(ctx, sym, verbose=False):
    t0 = time.time()
    run, run_path = load_run(sym)
    if not run:
        raise Fail("no holdermap run.json")
    ov = load_override(sym)
    n5 = ref(ctx, sym)
    warn = []
    alts = [o for o, _ in ctx.symhist.get(sym, [])]

    # ---- shareholding trend from the six filings
    fl, meta, miss = filings(sym, alts)
    if fl[-1] is None:
        raise Fail(f"missing shareholding XBRL for {', '.join(miss)} (latest quarter absent)")
    if miss:
        warn.append(f"{sym}: no shareholding filing for {', '.join(miss)} (not listed yet, or no parseable XBRL in any local copy); trend has {6 - len(miss)} quarters")
    isin = n5.get("isin") or meta.get("ISIN") or ""
    # ---- prices
    S, applied, px_notes, jumps, syms, catext, after = prices_for(ctx, sym, [isin, meta.get("ISIN")],
                                                                  ov.get("px_events", []))
    warn += px_notes
    W3 = iso(D(END).replace(year=D(END).year - 3))                    # 3 years back
    w3lo, w3hi = iso(D(W3) - dt.timedelta(days=10)), iso(D(W3) + dt.timedelta(days=70))
    gaps = [j for j in jumps if j.get("gap")]
    jumps = [j for j in jumps if not j.get("gap")]
    for j in gaps:
        warn.append(f"{sym}: no NSE trade {j['prev']} -> {j['d']} (trading gap); {j['move']:+.1f}% across it "
                    f"not treated as a day move")
    hard = [j for j in jumps if j["d"] >= w3lo]
    if hard:
        def why(j):
            near = [s.strip() for d, s, *_ in catext if abs((d - D(j["d"])).days) <= 10]
            x = next(s for s in S if s["d"] == j["d"])
            sug = f"; prev close/ex-day open = {j['raw'][0] / (x['o'] * x['f']):.4f}"
            return (f"{j['prev']}->{j['d']} {j['move']:+.1f}% (raw {j['raw'][0]}->{j['raw'][1]}"
                    f"{', CA: ' + '; '.join(near) if near else ''}{sug})")
        raise Fail("unexplained >25% adjusted day move: " + " | ".join(why(j) for j in hard))
    trend = []
    for r in fl:
        if r is None:
            continue
        b = on_or_before(S, r["fd"])
        bf = b["sf"] if b else S[0]["sf"]        # share factor; filed before the first traded day: listing basis
        trend.append(dict(q=r["q"], tot=r["tot"], nh=r["nh"], prom=r["prom"], fii=r["fii"], dii=r["dii"], ind=r["ind"],
                          oth=r["oth"], mf=r["mf"], ins=r["ins"], px=b["raw"] if b else None,
                          bf=round(bf, 6) if bf % 1 else int(bf),
                          f1=r["f1"], f2=r["f2"], aif=r["aif"], iS=r["iS"], iL=r["iL"], bc=r["bc"], nri=r["nri"],
                          dr=r["dr"], den=r["den"], dr_in_public=r["dr_in_public"], fdi=r["fdi"], fcos=r["fcos"],
                          filed=r["filed"]))
    tq = {t["q"]: t for t in trend}
    fl = [r for r in fl if r]
    last = fl[-1]
    lf = latest_filing(sym, alts) or last
    if lf["fd"] < last["fd"]:
        lf = last
    lb = on_or_before(S, lf["fd"])
    lsf = lb["sf"] if lb else S[0]["sf"]
    latest = dict(d=lf["fd"], tot=lf["tot"], nh=lf["nh"], prom=lf["prom"], fii=lf["fii"], dii=lf["dii"], ind=lf["ind"],
                  oth=lf["oth"], mf=lf["mf"], dr=lf["dr"], den=lf["den"], dr_in_public=lf["dr_in_public"],
                  fdi=lf["fdi"], fcos=lf["fcos"],
                  filed=lf["filed"],
                  sf=round(lsf, 6) if lsf % 1 else int(lsf), shares=int(round(lf["tot"] * lsf)))
    if lf["fd"] != last["fd"]:
        warn.append(f"{sym}: latest filing {lf['fd']} is after the last quarter-end {last['fd']}; "
                    f"trend stops at {last['fd']}, 'latest' carries it")
    TOT = int(round(last["tot"] * trend[-1]["bf"]))

    # ---- run periods and the open quarter
    periods = run.get("periods") or PERIODS
    rows = run["rows"] + [r for r in run.get("extra_rows", []) if r not in run["rows"]]
    pidx = {p: i for i, p in enumerate(periods)}
    oq = "Q3/2026" in pidx and any((r["shares"][pidx["Q3/2026"]] or 0) > 0 for r in rows
                                   if len(r["shares"]) > pidx["Q3/2026"])
    # holder columns are always the five closed quarters (+ the open one): a quarter the run lacks
    # (listed later, or a filing the run could not find) is null in every holder's s[] and listed in co.hq_missing
    if "Q2/2026" not in pidx:
        raise Fail(f"run periods {periods} lack Q2/2026, the last closed quarter")
    use = PERIODS[:5] + (["Q3/2026"] if oq else [])
    hq_missing = [HQ[i] for i, p in enumerate(use) if p not in pidx]
    if hq_missing:
        warn.append(f"{sym}: run has no holder column for {', '.join(hq_missing)} (run periods {periods}); null in s[]")
    NQ = len(use)
    L = NQ - 1                                                   # latest column
    hq = [HQ[PERIODS.index(p)] for p in use]

    def sh(r, i):
        j = pidx.get(use[i])
        if j is None:
            return 0
        return (r["shares"][j] if j < len(r["shares"]) else None) or 0

    def shn(r, i):                                   # as emitted: null where the run has no such column
        return None if use[i] not in pidx else sh(r, i)

    # ---- quarter-end prices (bhavcopy, adjusted to the END basis)
    prices = []
    for i, p in enumerate(PERIODS):
        if p == "Q3/2026":
            b = on_or_before(S, END)
            note = f"quarter still open on {END}; latest close used"
        else:
            b = on_or_before(S, PEND[p])
            note = ""
        if b is None:
            prices.append(dict(q=p, d=None, c=None, f=None, a=None, note=f"not yet listed (first close {S[0]['d']})"))
            continue
        prices.append(dict(q=p, d=b["d"], c=b["raw"], f=b["f"], a=round(b["c"], 4), note=note))
        rp = next((x for x in run.get("prices", []) if x.get("label") == p), None)
        if rp and p != "Q3/2026" and (rp.get("trade_date") != b["d"] or abs(rp.get("close", 0) - b["raw"]) > 0.005
                                      or abs((rp.get("factor") or 1) - b["sf"]) > 1e-6):
            warn.append(f"{sym}: run price {p} {rp.get('trade_date')} {rp.get('close')} x{rp.get('factor')} "
                        f"!= bhavcopy {b['d']} {b['raw']} x{b['sf']:g}")
    PX = [p["a"] for p in prices]                    # always six: the open quarter's price is known
    # free float per holdings quarter: latest total less that quarter's promoter shares (END basis)
    ffq = ["Jun-25", "Sep-25", "Dec-25", "Mar-26", "Jun-26", "Jun-26"]
    ff = [TOT - int(round(tq[q]["prom"] * tq[q]["bf"])) if q in tq else None for q in ffq]

    # ---- holders
    nice, cty = ov.get("nice", {}), ov.get("cty", {})
    gen_names = ov.get("generic_names", True)

    def nm(h):
        return nice.get(h) or (generic_name(h) if gen_names else h)

    def country(r):
        h = r["holder"]
        if h in cty:
            return cty[h]
        if "cty_default" in ov:
            return ov["cty_default"]
        if r["category"] == "Bank" and "public table: banks" in (r.get("evidence") or "").lower():
            return "IN"
        if r["category"] in FOREIGN:
            return ctx.reg.get(h, "")
        return "IN"

    def H(r, n=None):
        s = [shn(r, i) for i in range(NQ if n is None else n)]
        return dict(n=nm(r["holder"]), c=r["category"], sub=SUB.get(r["category"], r["category"]), cty=country(r),
                    s=s, ow=((r.get("owner") or "").split(" · ")[0]), rv=bool(r.get("review")),
                    alt=r.get("alternative") or "")

    def is_prom(r):   # e.g. PSUs: 'Republic of India' is filed as promoter (Table II), categorised Government
        return r.get("alternative") == "Promoter" or "promoter & promoter group table" in (r.get("evidence") or "").lower()

    def dom_bank(r):  # filing-mode runs put Indian banks (SEBI public table: Banks) in 'Bank', which data.py
        # treated as a foreign bank group; Bloomberg runs use 'Bank' for foreign groups only
        return r["category"] == "Bank" and ("public table: banks" in (r.get("evidence") or "").lower()
                                            or ctx.reg.get(r["holder"]) == "IN")

    def iepf(r):      # the IEPF authority is a statutory custodian of unclaimed shares, not an investor
        return "public table: iepf" in (r.get("evidence") or "").lower() or "investor education" in r["holder"].lower()
    fii = [H(r) for r in sorted([r for r in rows if r["category"] in FOREIGN and sh(r, L) > 0 and not is_prom(r)
                                 and not dom_bank(r)], key=lambda r: -sh(r, L))[:20]]
    dii = [H(r) for r in sorted([r for r in rows if (r["category"] in DOM or dom_bank(r)) and sh(r, L) > 0
                                 and not is_prom(r) and not iepf(r)], key=lambda r: -sh(r, L))[:20]]
    ind_excl = set(ov.get("ind_excl", []))
    creg = re.compile(ov["ind_company_regex"]) if ov.get("ind_company_regex") else ORG
    indr = [r for r in rows if (r["category"] == "Individual" or (r["category"] == "Promoter" and not creg.search(r["holder"])))
            and r["holder"] not in ind_excl and sh(r, 4) > 0]
    indl = []
    for r in sorted(indr, key=lambda r: -sh(r, 4))[:20]:
        d = H(r, 5)
        pt = ov.get("ind_patch", {}).get(d["n"])
        if pt:
            if pt.get("s0_from"):
                src = next(x for x in rows if x["holder"] == pt["s0_from"])
                d["s"][0] = src["shares"][pidx[use[0]]] if use[0] in pidx else None
            if pt.get("note"):
                d["note"] = pt["note"]
        indl.append(d)

    excl_all = set(ov.get("flow_excl", []))

    def flows(a, b, excl=set()):
        out = []
        for r in rows:
            if r["holder"] in excl or r["holder"] in excl_all:
                continue
            d = sh(r, b) - sh(r, a)
            if d == 0:
                continue
            tag = "New" if sh(r, a) == 0 and sh(r, b) > 0 else ("Exit" if sh(r, b) == 0 else "")
            out.append(dict(n=nm(r["holder"]), c=r["category"], sub=SUB.get(r["category"], r["category"]), cty=country(r),
                            d=d, v=round(d * PX[b] / 1e7, 2) if PX[b] is not None else None, a=sh(r, b), b=sh(r, a), t=tag))
        buy = sorted([o for o in out if o["d"] > 0], key=lambda o: -o["d"])[:25]
        sell = sorted([o for o in out if o["d"] < 0], key=lambda o: o["d"])[:25]
        return dict(buy=buy, sell=sell, all=out)

    fA = flows(3, 4) if "Q1/2026" in pidx else None
    fB = flows(4, 5, set(ov.get("flow_excl_B", []))) if oq else None

    gates = [dict(n=g["name"], d=g.get("detail", ""), ok=bool(g.get("passed"))) for g in run.get("gates", [])]
    recg = next((g for g in run.get("gates", []) if g["name"] == "category sums vs filing totals"), None)
    rec = [dict(c=r.get("category"), b=r.get("bloomberg_sum"), f=r.get("filing_total_x_factor"), r=r.get("ratio"),
                band=r.get("band"), note=r.get("note")) for r in (recg or {}).get("rows", [])]
    flag = [dict(n=nm(r["holder"]), c=r["category"], alt=r.get("alternative") or "", tier=r.get("tier"), sh=sh(r, L))
            for r in rows if r.get("review")]

    # ---- price layer
    e = D(END)
    y13 = iso(dt.date(e.year - 1, e.month - 1, e.day) if e.month > 1 else dt.date(e.year - 2, 12, e.day))  # 13 months
    series = [[s["d"], round(s["c"], 2), round(s["h"], 2), round(s["l"], 2)] for s in S if s["d"] >= y13]
    anch = {}
    for d in ANCHORS:
        b = on_or_before(S, d)
        anch[d] = [b["d"], round(b["c"], 4), b["raw"], "NSE bhavcopy"] if b else None
    lst = S[0]
    first_avail = lst["d"] <= "1995-01-31"          # bhavcopy.db starts 1994-12
    pre = [j for j in jumps if j["d"] < w3lo] + [dict(j, move=j["move"]) for j in gaps
                                               if (D(j["d"]) - D(j["prev"])).days > 180 and j["d"] < w3lo]
    listing = [lst["d"], round(lst["c"], 4), lst["raw"]]
    listing_note = since = None
    if pre:
        pre.sort(key=lambda j: j["d"])
        listing_note = (f"since-listing base withheld: {len(pre)} unexplained adjusted day move(s) or >180-day trading "
                        f"gap(s) before the 3-year window, last {pre[-1]['prev']}->{pre[-1]['d']} {pre[-1]['move']:+.1f}%: " +
                        "; ".join(f"{j['prev']}->{j['d']} {j['move']:+.1f}%" for j in pre[-5:]))
        warn.append(f"{sym}: {listing_note}")
        listing = None
        # the longest verified base instead: the close that completed the last unexplained move - every
        # day-on-day move after it is explained and adjusted. Only when it reaches further back than the
        # 3-year base by more than 30 days (otherwise the 3-year return already covers it).
        lj = pre[-1]
        b = S[idx_of(S, lj["d"])]
        if b["d"] < iso(D(W3) - dt.timedelta(days=30)):
            since = [b["d"], round(b["c"], 4), b["raw"],
                     f"close of {b['d']}, the day that completed the last unexplained move ({lj['prev']}->{lj['d']} "
                     f"{lj['move']:+.1f}%{', across a trading gap' if lj.get('gap') else ''}); every later day is "
                     f"explained and adjusted"]
    else:
        anch[lst["d"]] = [lst["d"], round(lst["c"], 4), lst["raw"], "NSE bhavcopy"]
    px_hist = dict(w3y=[[s["d"], round(s["c"], 4)] for s in S if w3lo <= s["d"] <= w3hi], listing=listing, since=since)
    if first_avail:
        px_hist["listing_is_first_available"] = True
    if listing_note:
        px_hist["note"] = listing_note
    w = [s for s in S if s["d"] > iso(D(END).replace(year=D(END).year - 1))]
    hi = max(w, key=lambda s: s["h"])
    lo = min(w, key=lambda s: s["l"])
    w52 = dict(hi=round(hi["h"], 2), hid=hi["d"], lo=round(lo["l"], 2), lod=lo["d"])

    # ---- results / valuation (filled by another agent when pipeline/inputs/results/<SYM>.json exists)
    val, earn = dict(bvps=None, dps=None, roe=None), None
    rp = RESULTS / f"{sym}.json"
    if rp.exists():
        R = json.load(open(rp))
        val = dict(bvps=R.get("bvps"), dps=R.get("dps_ttm"), roe=R.get("roe"), bs_date=R.get("bs_date"),
                   roe_basis=R.get("roe_basis"), dps_note=R.get("dps_basis"), equity_cr=R.get("equity_cr"))
        qs = R.get("quarters") or []
        if qs:
            earn = dict(q=[x.get("q") for x in qs], d=[x.get("d") for x in qs], rev=[x.get("rev") for x in qs],
                        pat=[x.get("pat") for x in qs],
                        pat_own=[x.get("pat_owners") if x.get("pat_owners") is not None else x.get("pat") for x in qs],
                        eps_rep=[x.get("eps") for x in qs],
                        basis=R.get("rev_basis"), format=R.get("format"), scope=R.get("scope"),
                        flags=R.get("flags") or [],
                        notes=(R.get("flags") or []) + [n for n in R.get("notes") or []
                                                        if "units: declared rounding" not in n
                                                        and "no iXBRL table" not in n])

    bse = str(meta.get("ScripCode") or ctx.bse.get(isin) or "")
    rf = ref(ctx, sym)
    co = dict(s=sym, n=run.get("company") or (rf.get("n") or "").rstrip(".") or sym, isin=isin, bse=bse,
              sector=rf.get("ind") or "", industry=rf.get("ind") or "", **membership(ctx, sym),
              bb=(run.get("holder_source") or "").lower().startswith("bloomberg"),
              fil=lf["fd"], fil_q=last["fd"], fil_missing=miss, hq_missing=hq_missing, oq=oq, px_end=END, bonus_after=[], listed=lst["d"],
              listed_is_first_available=first_avail, symbols=syms,
              ca=[[a["d"], a["r"], a["kind"]] for a in applied],
              px_gaps=[[j["prev"], j["d"], j["move"]] for j in gaps],
              shares_now=(ctx.nse_mcap.get(sym) or (TOT,))[0])
    out = dict(co=co, tot=TOT, ff=ff, px=[round(x, 4) if x is not None else None for x in PX], hq=hq, trend=trend, fii=fii, dii=dii, ind=indl,
               flows=dict(A=fA, B=fB), gates=gates, tiers=run.get("tiers", {}), rec=rec, prices=prices, flag=flag,
               fii_total=last["fii"], dii_total=last["dii"], gen=run.get("generated_at"),
               px_series=series, stock_anchor=anch, bench=ctx.bench, w52=w52, earn=earn, val=val, px_hist=px_hist,
               latest=latest)

    # ---- validation
    bse_code = meta.get("ScripCode") or ctx.bse.get(isin)
    v = validate(ctx, sym, out, fl, S, applied, bse_code)
    out["co"]["checks"] = v["checks"]
    info = dict(sym=sym, run=str(run_path), secs=round(time.time() - t0, 2), warn=warn, fail=v["fail"],
                events=[[a["d"], a["r"], a["kind"], a["src"], a["snapped"]] for a in applied], after=after)
    pxu = dict(shares=co["shares_now"], shares_filing=latest["shares"], qbase_close=(on_or_before(S, "2026-06-30") or {}).get("raw"),  # none if first traded after 30 Jun
               bonus_events=[[a["d"], float(a["r"])] for a in applied if a["kind"] in ("bonus", "split", "inferred")],
               price_events=[[a["d"], float(a["r"]), a["kind"]] for a in applied])
    return out, info, pxu


def validate(ctx, sym, out, fl, S, applied, bse_code=None):
    fail, checks = [], {}
    # 1. checksum: promoter + public + non-promoter-non-public == total, every filing; residual "others" >= 0
    bad = []
    for r in fl:
        s = r["prom"] + r["_pub"] + r["_npnp"]
        if s != r["tot"]:
            bad.append(f"{r['fd']}: prom+public+npnp {s} != total {r['tot']}")
        if r["oth"] < 0:
            bad.append(f"{r['fd']}: others {r['oth']} < 0")
        if r["prom"] + r["fii"] + r["dii"] + r["ind"] + r["oth"] + r["dr"] != r["tot"]:
            bad.append(f"{r['fd']}: categories + dr != total")
        if r["tot"] <= 0:
            bad.append(f"{r['fd']}: no total")
    checks["checksum"] = not bad
    fail += bad
    # 2. market cap vs NSE's own (PR archive mcap file on END): tot x close within 1%
    nse = ctx.nse_mcap.get(sym)
    b = S[-1]
    mine = out["latest"]["shares"] * b["raw"]
    if nse:
        issue, nclose, nmcap = nse
        dm = mine / nmcap - 1
        checks["mcap_vs_nse_pct"] = round(100 * dm, 3)
        checks["nse_issue_size"] = issue
        if abs(dm) > 0.01:
            fail.append(f"mcap {mine / 1e7:,.0f} cr vs NSE {nmcap / 1e7:,.0f} cr ({100 * dm:+.2f}%; filing "
                        f"{out['latest']['d']} shares {out['latest']['shares']:,} vs NSE issue size {issue:,})")
    else:
        checks["mcap_vs_nse_pct"] = None
        fail.append("no NSE mcap row on END (PR archive)")
    # 3. top-20 holder sums within the filing's category totals (last filed quarter, column 4)
    # comparable filing totals: FII list also holds foreign companies (SEBI non-institutions, B3);
    # the DII list also holds non-promoter Government holders (SEBI B4)
    lf = fl[-1]
    for k, tot in (("fii", lf["_fii_filed"] + lf["fcos"]), ("dii", lf["_dii_filed"] + lf["govt"])):
        s = sum(x["s"][4] for x in out[k])
        checks[k + "_top20_share"] = round(s / tot, 4) if tot else None
        if s > tot:
            fail.append(f"{k} top-20 sum {s:,} > filing {k.upper()}{' + foreign cos' if k == 'fii' else ' + govt'} "
                        f"{tot:,} at Jun-26 ({(100 * s / tot) if tot else float('inf'):.1f}%)")
    # 4. Jun-26 promoter % on SEBI's denominator (tot - C1) == NSE's published pr_and_prgrp (2 dp)
    # style 1 (DRs in C1 or none): prom/den IS the filed %; style 2 (depository inside the public
    # table): den also drops the depository, so the filed reconstruction is what NSE publishes
    den = lf["den"]
    pr = 100 * lf["prom"] / den
    pf = lf["filed"]["prom"]
    nse_pr = nse_promoter_pct(sym, lf["fd"])
    checks["dr_style"] = 2 if lf["dr_in_public"] else (1 if lf["dr"] else 0)
    checks["prom_pct"], checks["prom_pct_filed"], checks["prom_pct_nse"] = round(pr, 4), pf, nse_pr
    if nse_pr is None:
        checks["prom_vs_nse"] = None
    else:
        checks["prom_vs_nse"] = abs(pf - nse_pr) <= 0.01 + 1e-9
    # every quarter: filed promoter % vs NSE's published figure for that filing
    qbad, qn = [], 0
    for r in fl:
        npr = nse_promoter_pct(sym, r["fd"])
        if npr is None:
            continue
        qn += 1
        if abs(r["filed"]["prom"] - npr) > 0.01 + 1e-9:
            qbad.append(f"{r['q']} {r['filed']['prom']:.3f} vs {npr}")
    checks["prom_vs_nse_quarters"] = [qn - len(qbad), qn]
    if qbad:
        checks["prom_vs_nse"] = False
        fail.append("promoter % as filed vs NSE published: " + "; ".join(qbad))
    # 5. FII / DII / MF / promoter as filed vs BSE's published category % (same A+B+C2 basis):
    #    Jun-26 (bse_shp_all), Mar-26 and Mar-25 (bse_shp_hist) - across the SEBI format change
    tq0 = {r["q"]: r for r in fl}
    checks["bse"] = {}
    for q, base, qname in (("Jun-26", BSE_SHP_ALL, "June 2026"), ("Mar-26", BSE_SHP_HIST / "129", "Mar-26"),
                           ("Mar-25", BSE_SHP_HIST / "125", "Mar-25")):
        r = tq0.get(q)
        bse = bse_pcts(bse_code, base, qname) if r else None
        if not bse:
            continue
        f = r["filed"]
        dif = {k: round(f[k] - v, 3) for k, v in bse.items() if v is not None}
        checks["bse"][q] = dif
        bad = {k: v for k, v in dif.items() if abs(v) > 0.05 + 1e-9}
        lt = out["latest"]
        if bad and q == "Jun-26" and lt["d"] != r["fd"]:
            # BSE files a later intra-quarter filing under the same quarter name (SHRIPISTON: its
            # 'June 2026' record is the 20-Aug-2026 filing): compare with our latest filing instead
            dl = {k: round(lt["filed"][k] - v, 3) for k, v in bse.items() if v is not None}
            if all(abs(v) <= 0.05 + 1e-9 for v in dl.values()):
                checks["bse"][q] = dict(dl, note=f"BSE's June 2026 record is the {lt['d']} filing")
                bad = {}
        if bad:
            fail.append(f"vs BSE published {q} %: " + ", ".join(f"{k} {f[k]:.2f} vs {bse[k]:.2f} ({v:+.2f}pp)"
                                                               for k, v in bad.items()))
    # 6. category moves > 5pp Mar-26 -> Jun-26 (on den, DR-netted): listed for explanation
    tq = {r["q"]: r for r in fl}
    a, b2 = tq.get("Mar-26"), tq.get("Jun-26")
    moves = []
    if a and b2:
        for k in ("prom", "fii", "dii", "ind", "oth"):
            d = 100 * b2[k] / b2["den"] - 100 * a[k] / a["den"]
            if abs(d) > 5:
                moves.append([k, round(100 * a[k] / a["den"], 2), round(100 * b2[k] / b2["den"], 2), round(d, 2)])
        if moves:
            checks["moves_tot_chg_pct"] = round(100 * (b2["tot"] / a["tot"] - 1), 2)
    checks["moves"] = moves
    return dict(fail=fail, checks=checks)


BSE_SHP_ALL = HOME / "msci" / "data_dump" / "bse_shp_all"
BSE_SHP_HIST = HOME / "msci" / "data_dump" / "bse_shp_hist"


def nse_promoter_pct(sym, fdate):
    """NSE's published promoter % for the filing dated fdate (latest submission), from the freefloat index."""
    f = FF_SHP / f"{sym}.json"
    if not f.exists():
        return None
    if sym not in _SHP_IDX:
        _SHP_IDX[sym] = json.load(open(f))
    want = D(fdate).strftime("%d-%b-%Y").upper()
    c = [e for e in _SHP_IDX[sym] if (e.get("date") or "").upper() == want and e.get("pr_and_prgrp") not in (None, "", "-")]
    c.sort(key=lambda e: dt.datetime.strptime(e.get("submissionDate") or "01-JAN-2000", "%d-%b-%Y"), reverse=True)
    try:
        return float(c[0]["pr_and_prgrp"]) if c else None
    except ValueError:
        return None


def bse_pcts(code, base=None, qname="June 2026"):
    """BSE's published category % (of A+B+C2) for one quarter: FII, DII, MF subtotals and promoter."""
    d = (base or BSE_SHP_ALL) / str(code or "")
    if not code or not (d / "public.json").exists() or not (d / "summary.json").exists():
        return None
    try:
        summ = json.load(open(d / "summary.json"))
        if (summ.get("Table") or [{}])[0].get("Fld_qtrname") != qname:
            return None
        rows = json.load(open(d / "public.json")).get("Table1") or []
    except (ValueError, OSError):
        return None

    def sub(name):                    # the subtotal row: the largest unnamed row of that sub-category
        c = [r for r in rows if (r.get("Fld_SubCategory") or "").strip() == name and r.get("Fld_ShareHolderName") is None]
        r = max(c, key=lambda r: r.get("Fld_TotalNoOfShares") or 0, default=None)
        return r and r.get("Fld_TotalPercentageOf_A_B_C2")
    mf = next((r for r in rows if r.get("Fld_Code") == "B1a" and r.get("Fld_ShareHolderName") is None), None)
    prom = next((r for r in summ.get("Table1") or [] if (r.get("Fld_Code") or "") == "STA1A2"), None)
    out = dict(fii=sub("Institutions (Foreign)"), dii=sub("Institutions (Domestic)"),
               mf=mf and mf.get("Fld_TotalPercentageOf_A_B_C2"), prom=prom and prom.get("Fld_TotalPercentageOf_A_B_C2"))
    return out if any(v is not None for v in out.values()) else None


# --------------------------------------------------------------------------------------------
# universe + driver
# --------------------------------------------------------------------------------------------
def univ_row(ctx, sym, built=None):
    """One universe row. Uses the built file when present, else the filings + bhavcopy directly."""
    n5 = ref(ctx, sym)
    run, _ = load_run(sym)
    built_px = None
    if built:
        t = built.get("latest") or dict(built["trend"][-1], d=built["co"]["fil"], shares=built["tot"])
        fil, name, shf = t["d"], built["co"]["n"], t["shares"]
        tot = built["co"].get("shares_now") or shf
        rawc = built["stock_anchor"][END][2]
        qb = on_or_before_list(built, "2026-06-30")
    else:
        fl, meta, miss = filings(sym, [o for o, _ in ctx.symhist.get(sym, [])])
        have = [r for r in fl if r]
        if not have:                         # BSE-filed ("permitted") names: NSE's own issue size, no split
            nse = ctx.nse_mcap.get(sym)
            if not nse:
                return None, None
            S, applied, *_ = prices_for(ctx, sym, [n5.get("isin")])
            qb = on_or_before(S, "2026-06-30")
            rawc = S[-1]["raw"]
            row = dict(s=sym, n=n5.get("n", "").rstrip(".") or sym, m=round(nse[0] * rawc / 1e7), p=rawc,
                       q=round(100 * (rawc / qb["c"] - 1), 2) if qb else None, pr=None, fi=None, di=None,
                       h=None, fl=None, ok=None, sh=None, f=None, shares=None, shares_now=nse[0], dash=False,
                       note="no NSE shareholding XBRL (files with BSE); shares = NSE issue size", **membership(ctx, sym))
            return row, dict(shares=nse[0], shares_filing=None, qbase_close=qb["raw"] if qb else None,
                             bonus_events=[[a["d"], float(a["r"])] for a in applied if a["kind"] in ("bonus", "split", "inferred")],
                             price_events=[[a["d"], float(a["r"]), a["kind"]] for a in applied])
        alts = [o for o, _ in ctx.symhist.get(sym, [])]
        t = latest_filing(sym, alts) or have[-1]
        S, applied, *_ = prices_for(ctx, sym, [n5.get("isin"), meta.get("ISIN")])
        b0 = on_or_before(S, t["fd"])
        bf = b0["sf"] if b0 else S[0]["sf"]
        shf = int(round(t["tot"] * bf))
        tot = (ctx.nse_mcap.get(sym) or (shf,))[0]              # NSE issue size = current count
        fil, name = t["fd"], (run or {}).get("company") or n5.get("n", "").rstrip(".") or sym
        rawc = S[-1]["raw"]
        qb = on_or_before(S, "2026-06-30")
        qb = qb["c"] if qb else None
        built_px = dict(shares=tot, shares_filing=shf,
                        qbase_close=on_or_before(S, "2026-06-30")["raw"] if qb else None,
                        bonus_events=[[a["d"], float(a["r"])] for a in applied if a["kind"] in ("bonus", "split", "inferred")],
                        price_events=[[a["d"], float(a["r"]), a["kind"]] for a in applied])
    T = t.get("den") or t["tot"]                      # SEBI's denominator: total less C1 (DR custodian)
    row = dict(s=sym, n=name, m=round(tot * rawc / 1e7), p=rawc,
               q=round(100 * (rawc / qb - 1), 2) if qb else None,
               pr=round(100 * t["prom"] / T, 2), fi=round(100 * t["fii"] / T, 2), di=round(100 * t["dii"] / T, 2),
               h=len(run["rows"]) if run else None, fl=run.get("review_count") if run else None,
               ok=bool(run.get("all_passed")) if run else None, sh=t["nh"], f=fil, shares=shf, shares_now=tot,
               dash=(OUT_CO / f"{sym}.json").exists(), **membership(ctx, sym))
    return row, (None if built else built_px)


def on_or_before_list(built, d):
    # adjusted close on/before d from the stored series (13 months covers 30-Jun-2026)
    c = [r for r in built["px_series"] if r[0] <= d]
    return c[-1][1] if c else None


_UCACHE = {}


def write_univ(ctx, syms, pxu):
    rows, errs = [], {}
    for s in syms:
        f = OUT_CO / f"{s}.json"
        try:
            if f.exists():
                built = json.load(open(f))
                r, px = univ_row(ctx, s, built)
            else:                                 # filings + bhavcopy only; cached within a process
                if s not in _UCACHE:
                    _UCACHE[s] = univ_row(ctx, s, None)
                r, px = _UCACHE[s]
            if r is None:
                errs[s] = "no shareholding filing and no NSE mcap row"
                continue
            rows.append(r)
            if px and (s not in pxu or not f.exists()):
                pxu[s] = px
        except Fail as e:
            errs[s] = str(e)
        except Exception as e:  # noqa: BLE001 - report, never drop silently
            errs[s] = f"{type(e).__name__}: {e}"
    rows.sort(key=lambda u: -(u["m"] or 0))
    write_atomic(OUT_UNIV, json.dumps(rows, separators=(",", ":"), ensure_ascii=False))
    return rows, errs


def build_many(ctx, todo, pxu, rep, log=print):
    ok, failed, skipped = [], {}, []
    for s in todo:
        if not load_run(s)[0]:
            skipped.append(s)
            continue
        try:
            out, info, px = build(ctx, s)
        except Exception as e:  # noqa: BLE001 - Fail or a bug: reported, never silently dropped
            msg = str(e) if isinstance(e, Fail) else f"{type(e).__name__}: {e}"
            failed[s] = msg
            rep[s] = dict(sym=s, fatal=msg, at=time.strftime("%Y-%m-%dT%H:%M:%S"))
            f = OUT_CO / f"{s}.json"
            if f.exists():
                f.unlink()        # never leave a stale file for a company that now fails
            log(f"FAIL {s}: {msg}")
            continue
        write_atomic(OUT_CO / f"{s}.json", json.dumps(out, separators=(",", ":"), ensure_ascii=False))
        pxu[s] = px
        info["at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        info["bb"], info["oq"], info["earn"] = out["co"]["bb"], out["co"]["oq"], out["earn"] is not None
        rep[s] = info
        ok.append(s)
        if info["fail"]:
            log(f"CHECK {s}: " + " | ".join(info["fail"]))
    return ok, failed, skipped


def universe_syms(ctx):
    """Nifty 500 today + scheduled entrants + the NSE 100 runs + every exported company (leavers and
    --add extras keep their pages). REIT/InvIT entrants are skipped (unitholding patterns)."""
    return sorted((set(ctx.n500) | set(ctx.n500_add) | set(nse100()) | {p.stem for p in OUT_CO.glob("*.json")})
                  - reits(ctx))


def reits(ctx):
    return {s for s in ctx.n500_add
            if {r[0] for r in ctx.con.execute("select distinct series from bhav where symbol=?", (s,))} & {"RR", "IV"}}


def save(ctx, pxu, rep, univ=True):
    if univ:
        rows, uerr = write_univ(ctx, universe_syms(ctx), pxu)
        rep["_univ_errors"] = uerr
    write_atomic(OUT_PXU, json.dumps(pxu, separators=(",", ":")))
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(REPORT, json.dumps(rep, indent=1, default=str))


def stale(sym, rep):
    """A company needs (re)building when its run or results file is newer than its output."""
    run, rp = load_run(sym)
    if not run:
        return False
    src = max(rp.stat().st_mtime, (RESULTS / f"{sym}.json").stat().st_mtime if (RESULTS / f"{sym}.json").exists() else 0,
              (OVR / f"{sym}.json").stat().st_mtime if (OVR / f"{sym}.json").exists() else 0)
    f = OUT_CO / f"{sym}.json"
    if f.exists():
        return src > f.stat().st_mtime
    r = rep.get(sym) or {}
    if r.get("fatal"):                       # failed before: retry only when an input changed since
        at = r.get("at")
        return bool(at) and src > time.mktime(time.strptime(at, "%Y-%m-%dT%H:%M:%S"))
    return True


def watch(ctx, pxu, rep, hours, every=60):
    """Build Nifty 500 names as their run.json (and results) land, largest market cap first."""
    t_end = time.time() + hours * 3600
    logf = open(ROOT / "cache" / "company_watch.log", "a")

    def log(m):
        logf.write(time.strftime("%H:%M:%S ") + m + "\n")
        logf.flush()
    log(f"watch start ({hours}h)")
    code_mtime = Path(__file__).stat().st_mtime
    while time.time() < t_end:
        if Path(__file__).stat().st_mtime != code_mtime:     # never write outputs with stale code
            log("company.py changed on disk; watcher exits (restart it to pick up the new code)")
            break
        try:
            mcap = {u["s"]: u["m"] or 0 for u in json.loads(OUT_UNIV.read_text())} if OUT_UNIV.exists() else {}
            cand = [s for s in universe_syms(ctx) if stale(s, rep)]
            cand.sort(key=lambda s: -mcap.get(s, 0))
            if cand:
                for k in range(0, len(cand), 25):          # save progress every 25 companies
                    ok, failed, _ = build_many(ctx, cand[k:k + 25], pxu, rep, log)
                    save(ctx, pxu, rep)
                    log(f"built {len(ok)} failed {len(failed)}: {' '.join(ok)} | {' '.join(failed)}")
        except Exception as e:  # noqa: BLE001 - keep watching
            log(f"watch error {type(e).__name__}: {e}")
        time.sleep(every)
    log("watch end")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("syms", nargs="*")
    ap.add_argument("--nse100", action="store_true")
    ap.add_argument("--nifty500", action="store_true", help="the Nifty 500 today + its scheduled entrants")
    ap.add_argument("--add", nargs="+", default=[], metavar="SYM",
                    help="export companies outside the Nifty 500 (run.json in nse500-runs/<SYM>/ or inputs/extra/<SYM>/)")
    ap.add_argument("--univ-only", action="store_true")
    ap.add_argument("--no-univ", action="store_true")
    ap.add_argument("--watch", type=float, metavar="HOURS", help="poll for new runs/results for HOURS")
    a = ap.parse_args(argv)
    t0 = time.time()
    ctx = Ctx()
    todo = list(a.syms) + list(a.add)
    if a.nse100:
        todo += nse100()
    if a.nifty500:
        mcap = {u["s"]: u["m"] or 0 for u in json.loads(OUT_UNIV.read_text())} if OUT_UNIV.exists() else {}
        todo += sorted(set(ctx.n500) | (set(ctx.n500_add) - reits(ctx)), key=lambda s: -mcap.get(s, 0))
    todo = list(dict.fromkeys(todo))
    OUT_CO.mkdir(parents=True, exist_ok=True)
    pxu = json.loads(OUT_PXU.read_text()) if OUT_PXU.exists() else {}
    rep = json.loads(REPORT.read_text()) if REPORT.exists() else {}
    if a.watch:
        return watch(ctx, pxu, rep, a.watch)
    ok, failed, skipped = ([], {}, []) if a.univ_only else build_many(ctx, todo, pxu, rep,
                                                                       lambda m: print(m, file=sys.stderr))
    save(ctx, pxu, rep, univ=not a.no_univ)
    print(f"built {len(ok)}, failed {len(failed)}, no run {len(skipped)}, {time.time() - t0:.1f}s")
    for s, e in failed.items():
        print(f"  {s}: {e}")
    return ok, failed, skipped


if __name__ == "__main__":
    main()
