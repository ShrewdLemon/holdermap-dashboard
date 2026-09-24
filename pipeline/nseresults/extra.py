"""holdermap extensions to the vendored integrated-filing parser.

Written 2026-09-25 for pipeline/results.py. Keeps `financials.py` a verbatim
vendored copy; everything new lives here:

  * format from the iXBRL file name (INDAS / NBFC_INDAS / BANKING / LI / GI)
  * extra line items the vendored tables miss:
      - NBFC "Total Revenue From Operations" (revenue sub-lines precede it)
      - insurers: net premium (the revenue analogue) and "Profit / (loss) after tax"
      - paid-up equity share capital and face value (-> shares outstanding)
  * the statement of assets & liabilities (Sep/Mar filings): equity
    attributable to owners of the parent and its date
  * per field, the earliest-listed label pattern wins (not the first row)
  * the scale factor actually applied is returned, so balance-sheet and
    share-capital figures use the same unit interpretation as the P&L.
"""
from __future__ import annotations

import re

from .financials import (_table_rows, _row_label, parse_inr, ROUND_TO_CR,
                         _TBL_NONBANK, _TBL_BANK, _EPS_FIELDS)

_CAP = {
    "paidup_cr": [r"^paid[- ]?up equity (share )?capital"],
    "face_value": [r"^face value of equity share capital"],
}
_NCI = {"nci_cr": [r"attributable to non-controlling interests?$",
                   r"^(total )?profit \(?loss\)? of minority interest",
                   r"^share of minority interest"]}
_NONBANK = dict(_TBL_NONBANK)
_NONBANK["revenue_ops_cr"] = [r"^revenue from operations$", r"^total revenue from operations$"]
_BANK = dict(_TBL_BANK)
_INS = {
    "revenue_cr": [r"^total income$"],
    "net_premium_cr": [r"^net premium income$", r"^net premium written$",
                       r"^net premium$"],
    "gross_premium_cr": [r"^gross premium income$", r"^gross premiums written$"],
    "pbt_cr": [r"^profit\s*/?\s*\(?\s*loss\s*\)?\s*before tax$"],
    "pat_cr": [r"^profit\s*/?\s*\(?\s*loss\s*\)?\s*after tax and (before )?extraordinary",
               r"^profit\s*/?\s*\(?\s*loss\s*\)?\s*after tax$",
               r"^total profit .*for (the )?period$"],
    "pat_owners_cr": [r"attributable to owners of parent$"],
    "eps_basic": _TBL_NONBANK["eps_basic"] + [r"^basic and dilu\w* eps (after|before) extraordinary"],
}
_NONMONEY = _EPS_FIELDS | {"face_value"}


def filing_format(url: str) -> str:
    u = url.upper()
    for tag in ("NBFC_INDAS", "BANKING", "INDAS", "LI_", "GI_", "INSURANCE"):
        if f"INTEGRATED_FILING_{tag}" in u:
            return {"LI_": "LI", "GI_": "GI"}.get(tag, tag)
    return "OTHER"


def _blocks(rows):
    starts = [i for i, c in enumerate(rows)
              if _row_label(c)[1].startswith("date of start of reporting period")
              or _row_label(c)[1].startswith("date of end of reporting period") and
              (i == 0 or not _row_label(rows[i - 1])[1].startswith("date of start"))]
    out = []
    for bi, s in enumerate(starts):
        e = starts[bi + 1] if bi + 1 < len(starts) else len(rows)
        m = {}
        for cells in rows[s:min(s + 8, e)]:
            li, lab = _row_label(cells)
            if li is None or li + 1 >= len(cells):
                continue
            v = cells[li + 1].strip()
            if lab.startswith("date of start of reporting period"):
                m["start"] = v
            elif lab.startswith("date of end of reporting period"):
                m["end"] = v
            elif lab.startswith("nature of report"):
                m["scope"] = v
            elif lab.startswith("whether results are audited"):
                m["audited"] = v
        out.append((s, e, m))
    return out


def _first_value(cells, li):
    for c in cells[li + 1:]:
        v = parse_inr(c)
        if v is not None:
            return v
    return None


def _grab(rows, s, e, table):
    """First row in the block per (field, pattern); the EARLIEST-LISTED pattern
    wins. The vendored parser let row order win, so "Basic EPS from continuing
    operations" (listed second) beat the total "continuing and discontinued"
    EPS whenever it came first in the filing (TATACHEM Q4 FY25: -2.90 vs -2.19)."""
    best = {}   # field -> (pattern_idx, row_idx, value, label)
    for ri, cells in enumerate(rows[s:e]):
        li, label = _row_label(cells)
        if li is None or li + 1 >= len(cells):
            continue
        for field, pats in table.items():
            hit = next((pi for pi, p in enumerate(pats) if re.search(p, label)), None)
            if hit is None:
                continue
            v = _first_value(cells, li)
            if v is not None and (field not in best or hit < best[field][0]):
                best[field] = (hit, ri, v, cells[li])
            break
    raw = {k: b[2] for k, b in best.items()}
    lab_of = {k: b[3] for k, b in best.items()}
    return raw, lab_of


def _scale(declared_txt: str, raw: dict):
    declared = (declared_txt or "").split()[0].lower() if declared_txt else ""
    factor = ROUND_TO_CR.get(declared)
    note = ""
    # probe on P&L lines only: some filings put share capital in a wild unit
    # (CLEAN Q1 FY26 paid-up "106267259000000"), which must not drive the scale
    money = [v for k, v in raw.items() if k not in _NONMONEY and k not in ("paidup_cr", "nci_cr") and v]
    if money:
        probe = max(abs(v) for v in money)
        cands = [f for f in (factor, 1e-7, 0.01, 1.0, 0.1) if f]
        ok = [f for f in cands if 0.05 <= probe * f <= 5e6]
        if ok and factor not in ok:
            note = (f"declared rounding '{declared_txt}' implausible; values read "
                    f"with factor {ok[0]} to Rs cr")
            factor = ok[0]
    return factor, note


def parse_filing(html: str, url: str, want_scope: str) -> dict:
    """P&L fields for the reporting quarter + share capital + balance sheet."""
    fmt = filing_format(url)
    rows = _table_rows(html)
    rounding = ""
    for cells in rows:
        if len(cells) >= 2 and cells[0] and "level of rounding" in cells[0].lower():
            rounding = cells[1].strip()
            break
    blocks = _blocks(rows) or [(0, len(rows), {})]
    # P&L block: first block of the wanted scope that has a start date (duration)
    pl = [b for b in blocks if b[2].get("start")]
    chosen = next((b for b in pl if b[2].get("scope", "").lower().startswith(want_scope.lower()[:7])),
                  pl[0] if pl else blocks[0])
    s, e, bmeta = chosen
    bank = fmt == "BANKING" or (fmt == "OTHER" and bool(
        re.search(r">\s*(Total\s+)?[Ii]nterest\s+(earned|expen)", html)))
    ins = fmt in ("LI", "GI")
    table = dict(_BANK if bank else _INS if ins else _NONBANK)
    table.update(_CAP)
    table.update(_NCI)
    raw, labels = _grab(rows, s, e, table)
    factor, scale_note = _scale(rounding, raw)
    out = {"format": fmt, "bank": bank, "insurer": ins, "rounding": rounding,
           "factor": factor, "scale_note": scale_note,
           "scope": bmeta.get("scope", ""), "start": bmeta.get("start", ""),
           "end": bmeta.get("end", ""), "audited": bmeta.get("audited", ""),
           "labels": labels, "raw": raw}
    for k, v in raw.items():
        out[k] = v if k in _NONMONEY else (v * factor if factor else None)

    # ---- statement of assets & liabilities -----------------------------
    bs = None
    for bs_s, bs_e, bm in blocks:
        if bm.get("start") and not bm.get("end"):
            continue
        if not bm.get("scope", "").lower().startswith(want_scope.lower()[:7]):
            continue
        seg = rows[bs_s:bs_e]
        labs = [(_row_label(c), c) for c in seg]
        def find(pats, after=0):
            for idx, ((li, lab), c) in enumerate(labs):
                if idx < after or li is None or li + 1 >= len(c):
                    continue
                if any(re.search(p, lab) for p in pats):
                    v = _first_value(c, li)
                    if v is not None:
                        return idx, v, c[li]
            return None
        if bank or ins:
            cap = find([r"^capital$", r"^share capital$", r"^equity share capital$"])
            res = find([r"^reserves? (and|&) surplus$"])
            if cap and res and cap[0] < res[0] and res[0] - cap[0] <= 6:
                bs = {"equity_raw": cap[1] + res[1], "capital_raw": cap[1],
                      "equity_label": f"{cap[2]} + {res[2]}", "bs_date": bm.get("end", "")}
        else:
            tot = find([r"^total equity attributable to owners of (the )?parent",
                        r"^equity attributable to owners of (the )?parent$"])
            if tot is None:
                tot = find([r"^total equity$"])
            cap = find([r"^equity share capital$", r"^share capital$"])
            if tot and cap and cap[0] < tot[0]:
                bs = {"equity_raw": tot[1], "capital_raw": cap[1],
                      "equity_label": tot[2], "bs_date": bm.get("end", "")}
        if bs:
            break
    if bs and factor:
        bs["equity_cr"] = bs["equity_raw"] * factor
        bs["capital_cr"] = bs["capital_raw"] * factor
        out["bs"] = bs
    return out


# ------------------------------------------------------------------ raw XBRL
# Some integrated-filing rows (GI insurers, a few NBFCs) link only the XBRL
# instance - no rendered iXBRL table. Facts are read by tag for the exact
# quarter context (non-dimensional); XBRL values are absolute rupees.

_XTAGS = {
    "revenue_ops_cr": ["RevenueFromOperations"],
    "revenue_cr": ["Income"],
    "interest_earned_cr": ["InterestEarned"],
    "interest_expended_cr": ["InterestExpended"],
    "net_premium_cr": ["NetPremiumWritten", "NetPremiumIncome"],
    "gross_premium_cr": ["GrossPremiumsWritten", "GrossPremiumIncome"],
    "pbt_cr": ["ProfitBeforeTax", "ProfitOrLossBeforeTax"],
    "pat_cr": ["ProfitLossForPeriod", "ProfitLossForThePeriod", "ProfitLossAfterTax"],
    "pat_owners_cr": ["ProfitOrLossAttributableToOwnersOfParent"],
    "nci_cr": ["ProfitOrLossAttributableToNonControllingInterests"],
    "eps_basic": ["BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations",
                  "BasicEarningsLossPerShareFromContinuingOperations",
                  "BasicAndDilutedEPSAfterExtraordinaryItemsNetOfTaxExpenseForThePeriodNotToBeAnnualized",
                  "BasicEarningsPerShareAfterExtraordinaryItems"],
    "paidup_cr": ["PaidUpValueOfEquityShareCapital", "PaidUpEquityCapital"],
    "face_value": ["FaceValueOfEquityShareCapital"],
}


def parse_xbrl(xml: str, url: str, qe_iso: str) -> dict:
    fmt = filing_format(url)
    y, m, _ = qe_iso.split("-")
    qstart = f"{y}-{int(m) - 2:02d}-01"
    ctx = {}
    for cid, body in re.findall(r"<xbrli:context id=\"([^\"]+)\">(.*?)</xbrli:context>", xml, re.S):
        if "explicitMember" in body or "typedMember" in body:
            continue
        sd = re.search(r"startDate>([^<]+)<", body)
        ed = re.search(r"endDate>([^<]+)<", body)
        ins = re.search(r"instant>([^<]+)<", body)
        ctx[cid] = (sd.group(1).strip() if sd else None,
                    (ed or ins).group(1).strip() if (ed or ins) else None)
    facts_q, facts_i, meta = {}, {}, {}
    for tag, cid, val in re.findall(r"<[a-z-]+:([A-Za-z]+)\s[^>]*contextRef=\"([^\"]+)\"[^>]*>([^<]*)<", xml):
        c = ctx.get(cid)
        if not c:
            continue
        if c == (qstart, qe_iso):
            if tag == "LevelOfRounding":
                meta["rounding"] = val.strip()
            elif tag == "NatureOfReportStandaloneConsolidated":
                meta["scope"] = val.strip()
            facts_q.setdefault(tag, val.strip())
        elif c[1] == qe_iso:
            facts_i.setdefault(tag, val.strip())
    raw = {}
    for field, tags in _XTAGS.items():
        for t in tags:
            v = facts_q.get(t, facts_i.get(t) if field in ("paidup_cr",) else None)
            if v not in (None, ""):
                try:
                    raw[field] = float(v)
                    break
                except ValueError:
                    pass
    out = {"format": fmt, "bank": fmt == "BANKING", "insurer": fmt in ("LI", "GI"),
           "rounding": (meta.get("rounding", "") + " (XBRL instance: absolute rupees)").strip(),
           "factor": 1e-7, "scale_note": "", "scope": meta.get("scope", ""),
           "start": qstart, "end": qe_iso, "audited": "", "labels": {}, "raw": raw,
           "basis": "XBRL"}
    for k, v in raw.items():
        out[k] = v if k in _NONMONEY else v * 1e-7
    eq = facts_i.get("EquityAttributableToOwnersOfParent") or (
        facts_i.get("Equity") if not facts_i.get("NonControllingInterest") or
        float(facts_i.get("NonControllingInterest") or 0) == 0 else None)
    cap = facts_i.get("EquityShareCapital")
    if eq and cap:
        out["bs"] = {"equity_raw": float(eq), "capital_raw": float(cap),
                     "equity_label": "EquityAttributableToOwnersOfParent (XBRL)",
                     "bs_date": qe_iso, "equity_cr": float(eq) * 1e-7,
                     "capital_cr": float(cap) * 1e-7}
    return out
