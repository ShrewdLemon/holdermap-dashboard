# ---------------------------------------------------------------------------
# VENDORED (2nd hop) from `alpha` :: corpus/financials.py (sha256[:16] = 164ca4393926793a),
# copied 2026-09-25 into holdermap-dashboard/pipeline/nseresults/.
# holdermap changes: none in this file; balance-sheet / share-capital parsing
# lives in pipeline/nseresults/extra.py so this stays a verbatim copy.
#
# Original header follows.
# VENDORED from `steelglass` :: steelglass/financials.py
# source sha256[:16] = 6e93f8c472bb6e24
#
# alpha is deliberately self-contained: the exact corpus and gate code that
# produced the published results table is pinned in this repository's history,
# not in another repo's HEAD. Vendoring costs us hand-porting upstream fixes;
# for a study whose output is a frozen table, reproducibility wins.
#
# Changes from upstream:
#   - import path `.net` unchanged (corpus/ mirrors the package layout)
# ---------------------------------------------------------------------------
"""Reported quarterly financials, as filed - the hard-number backbone.

Two authentic NSE sources, both cached with provenance:

  1. Legacy structured results (through Q3 FY25):
       /api/corporates-financial-results?...&period=Quarterly
     Each row links a raw Ind-AS XBRL instance on nsearchives; facts are read
     by tag for the exact reporting period. Values arrive in absolute rupees.

  2. Integrated Filing results (Q3 FY25 onward, SEBI's current regime):
       /api/integrated-filing-results?index=equities&symbol=...
     Rows link NSE's rendered filing table (*_iXBRL_WEB.html). The document
     declares its own rounding ("Level of rounding ... Lakhs") and carries the
     statement as labelled rows; values are read from the FIRST occurrence of
     each label - the main statement precedes the segment tables, whose
     look-alike labels ("Revenue from operations") carry different figures.

Everything is normalised to Rs crore. Two derived fields are computed from
filed line items and flagged as such, never asserted as filed:
  EBITDA (non-banks) = profit before tax + depreciation + finance costs
  NII    (banks)     = interest earned - interest expended
NIM has no filed line item - it stays a guidance/commentary metric.
"""
from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from datetime import datetime

from .net import Fetcher

LIST_LEGACY = ("https://www.nseindia.com/api/corporates-financial-results"
               "?index=equities&symbol={sym}&period=Quarterly")
LIST_INTEGRATED = ("https://www.nseindia.com/api/integrated-filing-results"
                   "?index=equities&symbol={sym}")
PRIME = ["/", "/companies-listing/corporate-filings-financial-results"]
HEADERS = {"Accept": "*/*",
           "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-financial-results",
           "X-Requested-With": "XMLHttpRequest"}
ARCH = {"Referer": "https://www.nseindia.com/"}


@dataclass
class Actual:
    symbol: str
    fy: str                  # FY27
    quarter: str             # Q1
    period_start: str        # ISO
    period_end: str          # ISO
    scope: str               # Consolidated | Standalone
    audited: str
    bank: bool
    revenue_cr: float | None         # banks: total income
    revenue_ops_cr: float | None     # non-banks: revenue from operations
    interest_earned_cr: float | None
    interest_expended_cr: float | None
    interest_income_cr: float | None # NBFC lenders' interest income
    nii_cr: float | None             # computed (banks: earned-expended; NBFC: income-finance)
    pbt_cr: float | None
    pat_cr: float | None             # profit for the period
    pat_owners_cr: float | None      # attributable to owners, when stated
    eps_basic: float | None
    depreciation_cr: float | None
    finance_costs_cr: float | None
    ebitda_cr: float | None          # computed (non-banks)
    computed_note: str
    rounding: str
    basis: str               # XBRL | IXBRL_TABLE
    filed_at: str
    source_url: str

    def as_dict(self):
        return asdict(self)


# ------------------------------------------------------------------ helpers

def _dt(s: str, *fmts) -> datetime | None:
    for f in fmts:
        try:
            return datetime.strptime((s or "").strip(), f)
        except ValueError:
            continue
    return None


def fy_quarter(end: datetime) -> tuple[str, str]:
    """Indian FY/quarter for a period-end date. Jun->Q1, Sep->Q2, Dec->Q3, Mar->Q4."""
    q = {6: "Q1", 9: "Q2", 12: "Q3", 3: "Q4"}.get(end.month, f"M{end.month}")
    fy = end.year + 1 if end.month >= 4 else end.year
    return f"FY{str(fy)[-2:]}", q


def parse_inr(s: str) -> float | None:
    """Indian-formatted number; parentheses mean negative."""
    s = (s or "").strip().replace(" ", " ")
    if not s or s in ("-", "--"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace(",", "").strip()
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


ROUND_TO_CR = {"lakhs": 0.01, "lakh": 0.01, "crores": 1.0, "crore": 1.0,
               "millions": 0.1, "million": 0.1, "thousands": 0.0001,
               "actual": 1e-7, "absolute": 1e-7, "units": 1e-7, "billions": 100.0}


# -------------------------------------------------- legacy XBRL (pre-Q3FY25)

_XBRL_NONBANK = {
    "revenue_ops_cr": ["RevenueFromOperations"],
    "revenue_cr": ["Income"],
    "pbt_cr": ["ProfitBeforeTax"],
    "pat_cr": ["ProfitLossForPeriod"],
    "pat_owners_cr": ["ProfitOrLossAttributableToOwnersOfParent"],
    "eps_basic": ["BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations",
                  "BasicEarningsLossPerShareFromContinuingOperations"],
    "depreciation_cr": ["DepreciationDepletionAndAmortisationExpense"],
    "finance_costs_cr": ["FinanceCosts"],
}
_XBRL_BANK = {
    "revenue_cr": ["Income"],
    "interest_earned_cr": ["InterestEarned"],
    "interest_expended_cr": ["InterestExpended"],
    "pbt_cr": ["ProfitLossFromOrdinaryActivitiesBeforeTax"],
    "pat_cr": ["ProfitLossForThePeriod"],
    "pat_owners_cr": ["ProfitLossAfterTaxesMinorityInterestAndShareOfProfitLossOfAssociates"],
    "eps_basic": ["BasicEarningsPerShareAfterExtraordinaryItems",
                  "BasicEarningsPerShareBeforeExtraordinaryItems"],
}
_EPS_FIELDS = {"eps_basic"}


def parse_legacy_xbrl(xml_bytes: bytes, start: str, end: str, bank: bool) -> dict:
    """Facts for the exact duration [start, end] (ISO dates), in Rs crore."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return {}
    ctx_ok = set()
    for c in root.iter():
        if c.tag.endswith("}context"):
            s = e = None
            for p in c.iter():
                if p.tag.endswith("}startDate"):
                    s = (p.text or "").strip()
                elif p.tag.endswith("}endDate"):
                    e = (p.text or "").strip()
            if s == start and e == end:
                ctx_ok.add(c.get("id"))
    facts: dict[str, float] = {}
    for el in root.iter():
        if el.get("contextRef") in ctx_ok and el.text:
            tag = el.tag.split("}")[-1]
            if tag not in facts:
                try:
                    facts[tag] = float(el.text.strip())
                except ValueError:
                    pass
    out: dict[str, float] = {}
    table = _XBRL_BANK if bank else _XBRL_NONBANK
    for field, tags in table.items():
        for t in tags:
            if t in facts:
                v = facts[t]
                out[field] = v if field in _EPS_FIELDS else v / 1e7  # rupees -> crore
                break
    return out


# ------------------------------------- integrated filing table (Q3FY25 ->)

# "(loss)" is OPTIONAL in every label below. A prior version wrote
# `\(?loss\)?`, which makes the parens optional but still REQUIRES the word
# "loss" - so Bajaj Finance's "Basic earnings per share from continuing
# operations" (no "loss") matched nothing and its EPS came out blank.
_L = r"(?:\(loss\)\s*)?"          # optional "(loss) "
_PL = r"(?:\(?loss\)?\s*)?"       # optional, parens-and-word both optional
_TBL_NONBANK = {
    "revenue_ops_cr": [r"^revenue from operations$"],
    "revenue_cr": [r"^total income$"],
    "interest_income_cr": [r"^interest income$", r"^total interest income$"],  # NBFC lenders
    "pbt_cr": [r"^total profit " + _PL + r"before tax$",
               r"^profit\s*/?\s*" + _PL + r"before tax$"],
    "pat_cr": [r"^total profit " + _L + r"for (the )?period$",
               # insurers: "Profit / (loss) after tax and (before) Extraordinary items"
               r"^profit\s*/?\s*" + _PL + r"after tax and (before )?extraordinary"],
    "pat_owners_cr": [r"^profit or loss, attributable to owners of parent$"],
    "eps_basic": [r"^basic earnings " + _L + r"per share from continuing and discontinued",
                  r"^basic earnings " + _L + r"per share from continuing operations",
                  r"^basic and diluted eps"],   # insurers state one combined EPS
    "depreciation_cr": [r"^depreciation, depletion and amortisation expense"],
    "finance_costs_cr": [r"^finance costs?$"],
}
_TBL_BANK = {
    "revenue_cr": [r"^total income$"],
    "interest_earned_cr": [r"^total interest earned", r"^interest earned$"],
    "interest_expended_cr": [r"^interest expen(?:ded|ses)$"],
    "pbt_cr": [r"^(total )?profit \(?loss\)? (from ordinary activities )?before tax$"],
    "pat_cr": [r"^(total )?net profit \(?loss\)? for the period$",
               r"^(total )?profit \(?loss\)? for the period$",
               r"^net profit \(?loss\)? (from ordinary activities )?after tax$"],
    "pat_owners_cr": [r"after taxes?,? minority interest and share of profit",
                      r"attributable to owners of parent"],
    "eps_basic": [r"^basic(?! earnings per share from)( earnings per share)?( \(?after extraordinary items\)?)?$",
                  r"^basic earnings per share after extraordinary items",
                  r"^basic eps"],
}


def _table_rows(html: str) -> list[list[str]]:
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).replace(" ", " ").strip()
                 for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
        if any(cells):
            rows.append(cells)
    return rows


def _row_label(cells: list[str]) -> tuple[int | None, str]:
    for i, c in enumerate(cells[:3]):
        if c and re.search(r"[a-zA-Z]{3,}", c):
            return i, c.lower().rstrip(" :")
    return None, ""


def parse_integrated_table(html: str, bank: bool,
                           want_scope: str = "Consolidated") -> tuple[dict, dict]:
    """(fields, meta) from NSE's rendered filing table.

    Some documents bundle the standalone AND consolidated statements. Each
    statement block opens with "Date of start of reporting period" and states
    its own "Nature of report" - we parse only the block matching want_scope
    (falling back to whatever block exists). Within a block the FIRST
    occurrence of each label wins, anchoring to the main statement rather than
    the segment reconciliation that repeats the same labels.

    The value taken is each row's first numeric column (the reporting period;
    the next column is year-to-date). Rounding is taken from the document's
    own declaration - then sanity-checked, because a handful of filings
    declare "Crores" while carrying absolute rupees; the interpretation that
    lands revenue in a plausible band is used and recorded.
    """
    rows = _table_rows(html)
    meta: dict[str, str] = {}
    for cells in rows:
        if len(cells) >= 2 and cells[0] and cells[1]:
            key = cells[0].lower()
            if "level of rounding" in key:
                meta["rounding"] = cells[1].strip()

    # ---- statement blocks -------------------------------------------------
    starts: list[int] = []
    for i, cells in enumerate(rows):
        _, lab = _row_label(cells)
        if lab.startswith("date of start of reporting period"):
            starts.append(i)
    blocks: list[tuple[int, int, dict]] = []
    for bi, s in enumerate(starts):
        e = starts[bi + 1] if bi + 1 < len(starts) else len(rows)
        bmeta: dict[str, str] = {}
        for cells in rows[s:min(s + 8, e)]:
            li, lab = _row_label(cells)
            if li is None or li + 1 >= len(cells):
                continue
            val = cells[li + 1].strip()
            if lab.startswith("date of start of reporting period"):
                bmeta["start"] = val
            elif lab.startswith("date of end of reporting period"):
                bmeta["end"] = val
            elif lab.startswith("nature of report"):
                bmeta["scope"] = val
            elif lab.startswith("whether results are audited"):
                bmeta["audited"] = val
        blocks.append((s, e, bmeta))
    if not blocks:
        blocks = [(0, len(rows), {})]
    chosen = next((b for b in blocks
                   if b[2].get("scope", "").lower().startswith(want_scope.lower()[:7])),
                  blocks[0])
    s, e, bmeta = chosen
    meta.update(bmeta)

    # ---- fields within the chosen block -----------------------------------
    table = _TBL_BANK if bank else _TBL_NONBANK
    raw: dict[str, float] = {}
    for cells in rows[s:e]:
        li, label = _row_label(cells)
        if li is None or li + 1 >= len(cells):
            continue
        for field, pats in table.items():
            if field in raw:
                continue
            if any(re.search(p, label) for p in pats):
                val = None
                for c in cells[li + 1:]:
                    val = parse_inr(c)
                    if val is not None:
                        break
                if val is not None:
                    raw[field] = val
                break

    # ---- scale: declared rounding, sanity-checked -------------------------
    declared = (meta.get("rounding") or "").split()[0].lower()
    money = [v for k, v in raw.items() if k not in _EPS_FIELDS and v]
    factor = ROUND_TO_CR.get(declared)
    if money:
        probe = max(abs(v) for v in money)
        candidates = [f for f in (factor, 1e-7, 0.01, 1.0, 0.1) if f]
        ok = [f for f in candidates if 0.05 <= probe * f <= 5e6]
        if ok:
            if factor not in ok:
                meta["rounding"] = (f"{meta.get('rounding','?')} (declared) - "
                                    "values read as absolute INR" if ok[0] == 1e-7
                                    else f"{meta.get('rounding','?')} (declared, overridden)")
            factor = ok[0] if factor not in ok else factor
    out: dict[str, float] = {}
    for k, v in raw.items():
        if k in _EPS_FIELDS:
            out[k] = v
        elif factor is not None:
            out[k] = v * factor
    return out, meta


# --------------------------------------------------------------- assembly

def _derive(rec: dict, bank: bool, financial: bool = False) -> tuple[dict, str]:
    """Fill the sector-appropriate derived metric, from filed line items only.

    Banks       -> NII = interest earned - interest expended
    NBFC lenders -> NII = interest income - finance costs (EBITDA suppressed:
                   for a lender, interest is core cost, so PBT+finance+dep is
                   not a meaningful "EBITDA")
    Insurers    -> neither is meaningful; both left blank
    Other       -> EBITDA = PBT + depreciation + finance costs
    """
    note = ""
    if bank:
        ie, ix = rec.get("interest_earned_cr"), rec.get("interest_expended_cr")
        if ie is not None and ix is not None:
            rec["nii_cr"] = round(ie - ix, 2)
            note = "NII computed as interest earned - interest expended (both as filed)."
    elif financial:
        # Do not report EBITDA for financials - not a standard metric for them.
        ii, fin = rec.get("interest_income_cr"), rec.get("finance_costs_cr")
        if ii is not None and fin is not None:
            rec["nii_cr"] = round(ii - fin, 2)
            note = ("NII computed as interest income - finance costs (NBFC, both "
                    "as filed). EBITDA is not reported for financials.")
        else:
            note = "EBITDA not reported - not a standard metric for financials."
    else:
        pbt, dep, fin = rec.get("pbt_cr"), rec.get("depreciation_cr"), rec.get("finance_costs_cr")
        if pbt is not None and dep is not None and fin is not None:
            rec["ebitda_cr"] = round(pbt + dep + fin, 2)
            note = ("EBITDA computed as profit before tax + depreciation + finance "
                    "costs (all three as filed).")
    return rec, note


def quarterly_actuals(fetcher: Fetcher, symbol: str, bank_hint: bool | None = None,
                      financial: bool = False,
                      max_quarters: int = 10, verbose: bool = False) -> list[Actual]:
    f = fetcher
    f.prime("https://www.nseindia.com", PRIME)
    got: dict[tuple[str, str], Actual] = {}   # (period_end, scope) -> Actual

    # ---- integrated filings (current regime) -------------------------------
    r = f.get(LIST_INTEGRATED.format(sym=urllib.parse.quote(symbol, safe="")), HEADERS)
    rows = []
    try:
        j = r.json()
        rows = j.get("data") if isinstance(j, dict) else (j or [])
    except Exception:
        pass
    for row in rows or []:
        scope = (row.get("consolidated") or "").strip()
        url = (row.get("ixbrl") or "").strip()
        if scope not in ("Consolidated", "Standalone") or not url:
            continue  # governance filings interleave here
        qe = _dt(row.get("qe_Date"), "%d-%b-%Y", "%d-%B-%Y", "%d-%b-%y")
        if qe is None:
            continue
        rr = f.get(url, ARCH, binary=True)
        if rr.status != 200 or not rr.body:
            continue
        html = rr.body.decode("utf-8", "ignore")
        # bank format detection: the bank statement's signature line item
        bank = bank_hint if bank_hint is not None else bool(
            re.search(r">\s*(Total\s+)?[Ii]nterest\s+(earned|expen)", html))
        fields, meta = parse_integrated_table(html, bank, want_scope=scope)
        if not fields:
            if verbose:
                print(f"    ! {symbol} integrated {row.get('qe_Date')} {scope}: no fields parsed")
            continue
        start = _dt(meta.get("start", ""), "%d-%m-%Y", "%d-%b-%Y")
        fy, q = fy_quarter(qe)
        rec = {k: None for k in ("revenue_cr", "revenue_ops_cr", "interest_earned_cr",
                                 "interest_expended_cr", "interest_income_cr", "nii_cr",
                                 "pbt_cr", "pat_cr", "pat_owners_cr", "eps_basic",
                                 "depreciation_cr", "finance_costs_cr", "ebitda_cr")}
        rec.update(fields)
        rec, note = _derive(rec, bank, financial=financial)
        got[(qe.date().isoformat(), scope)] = Actual(
            symbol=symbol, fy=fy, quarter=q,
            period_start=start.date().isoformat() if start else "",
            period_end=qe.date().isoformat(), scope=scope,
            audited=meta.get("audited", row.get("audited") or ""),
            bank=bank, computed_note=note,
            rounding=meta.get("rounding", ""), basis="IXBRL_TABLE",
            filed_at=(row.get("broadcast_Date") or "")[:11].strip(),
            source_url=url, **rec)

    # ---- legacy XBRL (history) --------------------------------------------
    r = f.get(LIST_LEGACY.format(sym=urllib.parse.quote(symbol, safe="")), HEADERS)
    lrows = []
    try:
        j = r.json()
        lrows = j if isinstance(j, list) else (j.get("data") or [])
    except Exception:
        pass
    lparsed = []
    for row in lrows or []:
        to = _dt(row.get("toDate"), "%d-%b-%Y")
        frm = _dt(row.get("fromDate"), "%d-%b-%Y")
        if not to or not frm or not row.get("xbrl"):
            continue
        if to.year < 2017:   # pre-Ind-AS taxonomy; tags differ
            continue
        lparsed.append((to, frm, row))
    lparsed.sort(key=lambda t: t[0], reverse=True)
    for to, frm, row in lparsed:
        if len({qe for qe, _ in got}) >= max_quarters + 2:
            break
        scope = "Consolidated" if row.get("consolidated") == "Consolidated" else "Standalone"
        key = (to.date().isoformat(), scope)
        if key in got:   # integrated regime wins on overlap
            continue
        rr = f.get(row["xbrl"], ARCH, binary=True)
        if rr.status != 200 or not rr.body:
            continue
        bank = (row.get("bank") or "N").upper() in ("Y", "B")
        fields = parse_legacy_xbrl(rr.body, frm.date().isoformat(),
                                   to.date().isoformat(), bank)
        if not fields:
            if verbose:
                print(f"    ! {symbol} legacy {row.get('toDate')} {scope}: no facts matched")
            continue
        fy, q = fy_quarter(to)
        rec = {k: None for k in ("revenue_cr", "revenue_ops_cr", "interest_earned_cr",
                                 "interest_expended_cr", "interest_income_cr", "nii_cr",
                                 "pbt_cr", "pat_cr", "pat_owners_cr", "eps_basic",
                                 "depreciation_cr", "finance_costs_cr", "ebitda_cr")}
        rec.update(fields)
        rec, note = _derive(rec, bank, financial=financial)
        got[key] = Actual(
            symbol=symbol, fy=fy, quarter=q,
            period_start=frm.date().isoformat(), period_end=to.date().isoformat(),
            scope=scope, audited=row.get("audited") or "", bank=bank,
            computed_note=note, rounding="absolute INR (XBRL)", basis="XBRL",
            filed_at=(row.get("filingDate") or "")[:11].strip(),
            source_url=row["xbrl"], **rec)

    # ---- pick one record per quarter: Consolidated over Standalone ---------
    by_qe: dict[str, Actual] = {}
    for (qe, scope), a in got.items():
        cur = by_qe.get(qe)
        if cur is None or (cur.scope != "Consolidated" and scope == "Consolidated"):
            by_qe[qe] = a
    out = sorted(by_qe.values(), key=lambda a: a.period_end, reverse=True)[:max_quarters]
    return out
