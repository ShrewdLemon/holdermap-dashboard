#!/usr/bin/env python3
"""AMFI's half-yearly market-cap list: SEBI's large / mid / small cap categories for every listed company.

    python3 pipeline/amfi.py                    # newest list AMFI has published
    python3 pipeline/amfi.py --asof 2026-06-30  # a given half-year
    python3 pipeline/amfi.py --file x.xlsx      # parse a copy already downloaded

SEBI's circular of 6 Oct 2017 (SEBI/HO/IMD/DF3/CIR/P/2017/114) defines the categories by the rank of a
company's full market capitalisation: large cap = 1st-100th company, mid cap = 101st-250th, small cap =
251st onward. AMFI publishes the ranked list every six months (the average over Jan-Jun or Jul-Dec on
BSE, NSE and MSEI) and funds use it until the next one. It usually appears in the first week of July and
of January.

Writes pipeline/inputs/amfi_mcap.json: one row per company [rank, name, ISIN, BSE symbol, NSE symbol,
average market cap in Rs crore, SEBI category]. build.py matches our companies to it by ISIN (then NSE
symbol) and the landing page groups them: large, mid and small cap as AMFI lists them, with small cap
split at the 500th company into small (251st-500th) and micro (501st onward; NSE's Nifty Microcap 250
starts at the 501st). Standard library only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "pipeline" / "inputs" / "amfi_mcap.json"
URL = "https://portal.amfiindia.com/spages/AverageMarketCapitalization{:%d%b%Y}.xlsx"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
CATS = ("Large Cap", "Mid Cap", "Small Cap")


def half_years(today: dt.date):
    """Half-year ends on or before today, newest first."""
    y = today.year
    for yy in (y, y - 1, y - 2):
        for m, d in ((12, 31), (6, 30)):
            end = dt.date(yy, m, d)
            if end < today:
                yield end


def fetch(asof: dt.date) -> bytes | None:
    url = URL.format(asof)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    if not body.startswith(b"PK"):  # an HTML page, not the spreadsheet
        return None
    return body


def cells(xlsx: bytes):
    """Rows of the first sheet as {column letter: text}, from the raw OOXML (no openpyxl)."""
    z = zipfile.ZipFile(io.BytesIO(xlsx))
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
            shared.append("".join(t.text or "" for t in si.iter("{%s}t" % NS["m"])))
    sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    for row in sheet.iter("{%s}row" % NS["m"]):
        out = {}
        for c in row.findall("m:c", NS):
            col = re.match(r"[A-Z]+", c.get("r")).group(0)
            t, v = c.get("t"), c.find("m:v", NS)
            if t == "inlineStr":
                out[col] = "".join(x.text or "" for x in c.iter("{%s}t" % NS["m"]))
            elif v is not None:
                out[col] = shared[int(v.text)] if t == "s" else v.text
        yield out


def parse(xlsx: bytes):
    rows = list(cells(xlsx))
    head = next((i for i, r in enumerate(rows) if any("ISIN" == (v or "").strip() for v in r.values())), None)
    if head is None:
        raise SystemExit("no header row with ISIN: AMFI changed the layout")
    h = {(v or "").strip().lower(): k for k, v in rows[head].items()}
    col = lambda pre: next(k for name, k in h.items() if name.startswith(pre))
    cR, cN, cI = col("sr"), col("company"), col("isin")
    cB, cS = col("bse symbol"), col("nse symbol")
    cA, cC = col("average of all"), col("categori")
    title = next((v for r in rows[:head] for v in r.values() if v), "")
    basis = re.sub(r"\s+", " ", rows[head][cC].strip())  # AMFI's heading names the SEBI circular
    out = []
    for r in rows[head + 1:]:
        rk = (r.get(cR) or "").strip()
        if not rk.isdigit():
            continue
        sym = lambda k: None if (r.get(k) or "-").strip() in ("-", "") else r[k].strip()
        out.append([int(rk), re.sub(r"\s+", " ", (r.get(cN) or "").strip()), (r.get(cI) or "").strip(),
                    sym(cB), sym(cS), round(float(r.get(cA) or 0), 2), (r.get(cC) or "").strip()])
    return title, basis, out


def check(rows):
    """The list must be SEBI's rule applied as written: ranked by market cap, 100 large, 150 mid, the rest small."""
    ranks = [r[0] for r in rows]
    assert ranks == list(range(1, len(rows) + 1)), "ranks are not 1..n"
    assert all(rows[i][5] >= rows[i + 1][5] for i in range(len(rows) - 1)), "not sorted by market cap"
    want = lambda k: CATS[0] if k <= 100 else CATS[1] if k <= 250 else CATS[2]
    bad = [r[:2] + [r[6]] for r in rows if r[6] != want(r[0])]
    assert not bad, f"category does not follow the rank: {bad[:5]}"
    assert len({r[2] for r in rows}) == len(rows), "duplicate ISINs"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--asof", help="half-year end, e.g. 2026-06-30")
    ap.add_argument("--file", help="parse this .xlsx instead of downloading")
    a = ap.parse_args()
    if a.file:
        body = Path(a.file).read_bytes()
        m = re.search(r"(\d{2})([A-Za-z]{3})(\d{4})", Path(a.file).name)
        asof = dt.datetime.strptime("".join(m.groups()), "%d%b%Y").date() if m else None
    else:
        tries = [dt.date.fromisoformat(a.asof)] if a.asof else list(half_years(dt.date.today()))
        body = asof = None
        for d in tries:
            body = fetch(d)
            if body:
                asof = d
                break
        if not body:
            raise SystemExit("no AMFI list found for " + ", ".join(map(str, tries)))
    title, basis, rows = parse(body)
    check(rows)
    start = asof.replace(month=1 if asof.month == 6 else 7, day=1)
    rec = {
        "title": title,
        "asof": asof.isoformat(),
        "period": f"{start:%b}–{asof:%b %Y}",
        "category_basis": basis,
        "rule": "SEBI circular SEBI/HO/IMD/DF3/CIR/P/2017/114 of 6 Oct 2017: large cap 1st-100th, "
                "mid cap 101st-250th, small cap 251st onward, by full market capitalisation",
        "source": URL.format(asof),
        "sha256": hashlib.sha256(body).hexdigest(),
        "retrieved": dt.date.today().isoformat(),
        "cols": ["rank", "name", "isin", "bse", "nse", "avg_mcap_cr", "category"],
        "rows": rows,
    }
    # One company per line keeps the half-yearly diffs readable.
    txt = json.dumps({k: v for k, v in rec.items() if k != "rows"}, ensure_ascii=False)[:-1]
    txt += ',"rows":[\n' + ",\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n]}\n"
    OUT.write_text(txt)
    n = {c: sum(r[6] == c for r in rows) for c in CATS}
    print(f"{OUT.relative_to(ROOT)}: {len(rows)} companies, {rec['period']} "
          f"({n['Large Cap']} large, {n['Mid Cap']} mid, {n['Small Cap']} small); "
          f"cut-offs Rs {rows[99][5]:,.0f} cr (100th), {rows[249][5]:,.0f} cr (250th), {rows[499][5]:,.0f} cr (500th)")


if __name__ == "__main__":
    sys.exit(main())
