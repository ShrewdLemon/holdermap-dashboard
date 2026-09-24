"""Live price layer: the latest NSE closes, written to dashboard/site/prices.js.

    python3 pipeline/live.py            # fetch what is missing, write prices.js
    python3 pipeline/live.py --offline  # use only the cache (no network)

src/data.json is the holdings snapshot of one holdermap run and never changes
here. This script overlays prices on it at build time: the page reads
window.__PX__ when prices.js is present and falls back to the snapshot's own
prices when it is not (a plain local build).

Sources (only nsearchives.nseindia.com is contacted; www.nseindia.com sits
behind Akamai and is never used):
  - equities: the daily UDiFF bhavcopy zip (the older cmDDMONYYYYbhav.csv.zip
    before 8 Jul 2024), ClsPric/HghPric/LwPric on the EQ row;
  - indices: ind_close_all_DDMMYYYY.csv, the "Nifty 50" and "Nifty 500" rows.

Every fetched day is reduced to the closes the page needs and kept in
cache/closes.json, so a rerun asks NSE only for days it has not seen. CI keeps
that file in S3 between builds. A 404 on a weekday is a holiday (or a file not
published yet): the walk steps back a day. Anything else (403, 5xx, an HTML
page with a 200) is a refusal, and the build falls back to the cache rather
than publish a price from the wrong day.

ANANDRATHI closes are bonus-adjusted: divide by 2 for each 1:1 bonus whose
ex-date is after the trade date. Add any new bonus or split to BONUSES.
"""
from __future__ import annotations

import argparse
import calendar
import csv
import datetime as dt
import io
import json
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "data.json"
UNIV = ROOT / "pipeline" / "inputs" / "univ.json"
BHAV_AR = ROOT / "pipeline" / "inputs" / "bhav_ar.json"
CACHE = ROOT / "cache" / "closes.json"
OUT = ROOT / "dashboard" / "site" / "prices.js"

SYM = "ANANDRATHI"
LISTED = "2021-12-14"
BONUSES = [("2025-03-05", 2.0), ("2026-06-03", 2.0)]  # (ex-date, share multiplier)
OPEN_Q_END = "2026-09-30"  # end of the quarter the holdings snapshot calls "to date" (Q3/2026)
MAX_JUMP = 0.25  # a day-on-day move above this in the adjusted series means a missing corporate action

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
UDIFF = "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{:%Y%m%d}_F_0000.csv.zip"
OLD_BHAV = "https://nsearchives.nseindia.com/content/historical/EQUITIES/{y}/{m}/cm{d:%d}{m}{y}bhav.csv.zip"
INDEX = "https://nsearchives.nseindia.com/content/indices/ind_close_all_{:%d%m%Y}.csv"
UDIFF_FROM = dt.date(2024, 7, 8)
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


class Refused(Exception):
    """NSE answered with something other than the file or a clean 404."""


def factor(day: str) -> float:
    f = 1.0
    for ex, m in BONUSES:
        if day < ex:
            f *= m
    return f


def _get(url: str) -> bytes | None:
    """The body, or None on a 404. Raises Refused on anything else."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.nseindia.com/"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code >= 500 and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            raise Refused(f"{url}: HTTP {e.code}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            raise Refused(f"{url}: {e}") from e
    raise Refused(url)


def fetch_equities(day: dt.date, symbols: set[str]) -> dict[str, list[float]] | None:
    """{symbol: [close, high, low]} for the EQ rows, or None if no file for that day."""
    if day >= UDIFF_FROM:
        body = _get(UDIFF.format(day))
        cols = ("TckrSymb", "SctySrs", "ClsPric", "HghPric", "LwPric")
    else:
        m = day.strftime("%b").upper()
        body = _get(OLD_BHAV.format(y=day.year, m=m, d=day))
        cols = ("SYMBOL", "SERIES", "CLOSE", "HIGH", "LOW")
    if body is None:
        return None
    if body[:2] != b"PK":
        raise Refused(f"bhavcopy {day}: not a zip ({body[:60]!r})")
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        text = z.read(z.namelist()[0]).decode("utf-8", "replace")
    out: dict[str, list[float]] = {}
    for row in csv.DictReader(io.StringIO(text)):
        row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
        s = row.get(cols[0])
        if s in symbols and row.get(cols[1]) in ("EQ", "BE", "BZ") and (s not in out or row[cols[1]] == "EQ"):
            out[s] = [float(row[cols[2]]), float(row[cols[3]]), float(row[cols[4]])]
    return out


def fetch_indices(day: dt.date) -> dict[str, float] | None:
    body = _get(INDEX.format(day))
    if body is None:
        return None
    text = body.decode("utf-8", "replace")
    if not text.startswith("Index Name"):
        raise Refused(f"index file {day}: unexpected body ({text[:60]!r})")
    out = {}
    for row in csv.DictReader(io.StringIO(text)):
        name = (row.get("Index Name") or "").strip().lower()
        key = {"nifty 50": "n50", "nifty 500": "n500"}.get(name)
        if key and row.get("Closing Index Value"):
            out[key] = float(row["Closing Index Value"])
    return out


class Closes:
    """cache/closes.json: {"YYYY-MM-DD": {"eq": {...}, "ix": {...}} | {"holiday": true}}."""

    def __init__(self, path: Path, symbols: set[str], today: dt.date, offline: bool):
        self.path, self.symbols, self.today, self.offline = path, symbols, today, offline
        self.days = json.loads(path.read_text()) if path.exists() else {}
        self.fetched = 0
        self.refused: list[str] = []

    def day(self, d: dt.date) -> dict | None:
        """The closes for d, or None if the market did not trade (or it is not published yet)."""
        if d.weekday() >= 5 or d > self.today:
            return None
        key = d.isoformat()
        got = self.days.get(key)
        if got is not None:
            return None if got.get("holiday") else got
        if self.offline or self.refused:
            return None
        try:
            eq = fetch_equities(d, self.symbols)
            ix = fetch_indices(d) if eq is not None else None
        except Refused as e:
            self.refused.append(str(e))
            print(f"warning: {e}; using the cache from here on", file=sys.stderr)
            return None
        self.fetched += 1
        if eq is None:
            # Only a past day's 404 is a holiday; today's file may simply not be out yet.
            if (self.today - d).days >= 4:
                self.days[key] = {"holiday": True}
            return None
        if SYM not in eq:
            print(f"warning: {d}: {SYM} missing from the bhavcopy", file=sys.stderr)
        self.days[key] = {"eq": eq, "ix": ix or {}}
        return self.days[key]

    def on_or_before(self, d: dt.date, lookback: int = 10) -> tuple[dt.date, dict] | None:
        for i in range(lookback):
            x = d - dt.timedelta(days=i)
            got = self.day(x)
            if got is not None:
                return x, got
        return None

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(dict(sorted(self.days.items())), separators=(",", ":")))


def months_back(d: dt.date, n: int) -> dt.date:
    y, m = divmod(d.year * 12 + d.month - 1 - n, 12)
    m += 1
    return dt.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def quarter_start(d: dt.date) -> dt.date:
    return dt.date(d.year, 3 * ((d.month - 1) // 3) + 1, 1)


def build(today: dt.date, offline: bool = False) -> dict:
    D = json.loads(DATA.read_text())
    univ = {u["sym"]: u for u in json.loads(UNIV.read_text())}
    symbols = set(univ) | {SYM}
    C = Closes(CACHE, symbols, today, offline)

    # ---- ANANDRATHI daily series (adjusted): the snapshot's series, extended with every new trading day
    series = {r[0]: list(r) for r in D["px_series"]}
    raw = {r[0]: r[4] for r in json.loads(BHAV_AR.read_text())}  # raw closes, listing to Aug 2026
    first = min(series)  # older cached days are return bases only, not part of the daily series
    for day, (c, h, l) in ((k, v["eq"][SYM]) for k, v in C.days.items() if not v.get("holiday") and SYM in v.get("eq", {})):
        f = factor(day)
        raw[day] = c
        if day >= first:
            series[day] = [day, round(c / f, 2), round(h / f, 2), round(l / f, 2)]
    last = dt.date.fromisoformat(max(series))
    d = last + dt.timedelta(days=1)
    while d <= today:
        got = C.day(d)
        if got and SYM in got["eq"]:
            c, h, l = got["eq"][SYM]
            f = factor(d.isoformat())
            series[d.isoformat()] = [d.isoformat(), round(c / f, 2), round(h / f, 2), round(l / f, 2)]
            raw[d.isoformat()] = c
        d += dt.timedelta(days=1)
    rows = [series[k] for k in sorted(series)]
    for a, b in zip(rows, rows[1:]):
        if abs(b[1] / a[1] - 1) > MAX_JUMP:
            raise SystemExit(f"{SYM} moved {100 * (b[1] / a[1] - 1):.1f}% from {a[0]} to {b[0]}: "
                             "add the corporate action to BONUSES in pipeline/live.py")
    now_row, prev_row = rows[-1], rows[-2]
    asof = dt.date.fromisoformat(now_row[0])

    def adj_close(day: dt.date) -> tuple[str, float, float, str] | None:
        """(trade date, adjusted, raw, source) on or before day, from local data first."""
        for i in range(10):
            k = (day - dt.timedelta(days=i)).isoformat()
            if k in raw:
                return k, round(raw[k] / factor(k), 4), raw[k], "NSE bhavcopy"
            if k in series:
                return k, series[k][1], round(series[k][1] * factor(k), 2), "NSE bhavcopy"
        return None

    def index_on(day: str) -> dict:
        b = D["bench"]
        known = {k: b[n][day] for k, n in (("n50", "nifty50"), ("n500", "nifty500")) if day in b.get(n, {})}
        if len(known) == 2:
            return known
        got = C.day(dt.date.fromisoformat(day))
        return {**(got or {}).get("ix", {}), **known} if got else known

    now_ix = index_on(now_row[0])

    # ---- return bases
    per = [("1m", "1 month", months_back(asof, 1), None), ("3m", "3 months", months_back(asof, 3), None),
           ("6m", "6 months", months_back(asof, 6), None), ("ytd", "Year to date", dt.date(asof.year - 1, 12, 31), None),
           ("1y", "1 year", months_back(asof, 12), None), ("3y", "3 years, annualised", months_back(asof, 36), 3),
           ("sl", "Since listing, annualised", dt.date.fromisoformat(LISTED), None)]
    bases = []
    for k, label, target, yrs in per:
        got = adj_close(target)
        if got is None:
            continue
        bd, s, sraw, src = got
        if k == "sl":
            yrs = (asof - dt.date.fromisoformat(bd)).days / 365.25
        ix = index_on(bd)
        bases.append(dict(k=k, l=label, d=bd, s=s, sraw=sraw, ssrc=src, n50=ix.get("n50"), n500=ix.get("n500"), yrs=yrs))

    # ---- 52-week range (intraday, adjusted)
    y1 = months_back(asof, 12).isoformat()
    win = [r for r in rows if r[0] > y1]
    hi = max(win, key=lambda r: r[2])
    lo = min(win, key=lambda r: r[3])

    # ---- open quarter: the snapshot's "Q3/2026 to date" values use the close on or before its quarter end
    oq_row = [r for r in rows if r[0] <= OPEN_Q_END][-1]
    oq = dict(d=oq_row[0], c=oq_row[1], raw=round(oq_row[1] * factor(oq_row[0]), 2), open=oq_row[0] < OPEN_Q_END and asof.isoformat() < OPEN_Q_END)

    # ---- universe: latest close, quarter-to-date change, market cap
    latest = C.on_or_before(asof) or (None, {"eq": {}})
    qbase_day = quarter_start(asof) - dt.timedelta(days=1)
    if qbase_day.isoformat() == "2026-06-30":
        qbase = {s: [u["close_q2"]] for s, u in univ.items() if u.get("close_q2")}
    else:
        got = C.on_or_before(qbase_day)
        qbase = got[1]["eq"] if got else {}
    out_u, stale = {}, []
    for s, u in univ.items():
        px = (latest[1]["eq"].get(s) or [None])[0]
        if px is None:
            stale.append(s)
            continue
        base = (qbase.get(s) or [None])[0]
        q = round(100 * (px / base - 1), 2) if base else None
        if q is not None and abs(q) > 60:
            print(f"warning: {s} QTD {q}% looks like a split or bonus; shown as n/a", file=sys.stderr)
            q = None
        out_u[s] = [px, q, round(u["shares"] * px / 1e7)]
    if stale:
        print(f"note: no {asof} close for {len(stale)} symbols, keeping snapshot prices: {', '.join(stale[:8])}", file=sys.stderr)

    C.save()
    return dict(
        asof=asof.isoformat(),
        built=dt.datetime.now(IST).isoformat(timespec="minutes"),
        src="NSE bhavcopy and NSE index closes (nsearchives.nseindia.com)",
        stale=bool(C.refused),
        now=dict(d=now_row[0], c=now_row[1], prev=prev_row[1], prevd=prev_row[0], n50=now_ix.get("n50"), n500=now_ix.get("n500")),
        oq=oq,
        series=[r for r in rows if r[0] >= months_back(asof, 13).isoformat()],
        w52=dict(hi=hi[2], hid=hi[0], lo=lo[3], lod=lo[0]),
        bases=bases,
        univ=out_u,
        qbase=qbase_day.isoformat(),
        fetched=C.fetched,
    )


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--offline", action="store_true", help="use only cache/closes.json")
    ap.add_argument("--today", help="YYYY-MM-DD (default: today in IST)")
    a = ap.parse_args(argv)
    today = dt.date.fromisoformat(a.today) if a.today else dt.datetime.now(IST).date()
    px = build(today, a.offline)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("window.__PX__ = " + json.dumps(px, separators=(",", ":")) + ";\n")
    n = px["now"]
    print(f"prices.js: {SYM} {n['c']} on {n['d']} (prev {n['prev']}), Nifty 50 {n['n50']}, Nifty 500 {n['n500']}; "
          f"{len(px['univ'])}/101 universe closes; {px['fetched']} NSE days fetched"
          + ("; NSE REFUSED, cache used" if px["stale"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
