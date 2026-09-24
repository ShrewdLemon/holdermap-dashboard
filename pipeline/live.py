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
DATA = ROOT / "src" / "data.json"            # ANANDRATHI snapshot (fallback when src/co/ is empty)
CO_DIR = ROOT / "src" / "co"                  # one holdings snapshot per company (pipeline/company.py)
UNIV = ROOT / "pipeline" / "inputs" / "univ.json"
PXU = ROOT / "pipeline" / "inputs" / "px_universe.json"  # shares, 30-Jun close, bonus events per symbol
IDX_HIST = ROOT / "pipeline" / "inputs" / "index_hist.json"  # Nifty 50 / 500 daily closes since inception
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
        cols = ("TckrSymb", "SctySrs", "ClsPric", "HghPric", "LwPric", "PrvsClsgPric")
    else:
        m = day.strftime("%b").upper()
        body = _get(OLD_BHAV.format(y=day.year, m=m, d=day))
        cols = ("SYMBOL", "SERIES", "CLOSE", "HIGH", "LOW", "PREVCLOSE")
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
            out[s] = [float(row[cols[2]]), float(row[cols[3]]), float(row[cols[4]]), float(row.get(cols[5]) or 0)]
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
        if got is not None and not got.get("holiday"):
            # A day cached for a smaller universe is refetched while it is recent.
            missing = len(self.symbols - set(got["eq"]))
            old = got.get("v", 1) < 2  # cached before NSE's previous close was kept
            if (missing <= 0.2 * len(self.symbols) and not old) or (self.today - d).days > 10 or self.offline or self.refused:
                return got
        elif got is not None:
            return None
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
        self.days[key] = {"eq": eq, "ix": ix or {}, "v": 2}
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


def load_companies() -> dict[str, dict]:
    cos = {f.stem: json.loads(f.read_text()) for f in sorted(CO_DIR.glob("*.json"))} if CO_DIR.exists() else {}
    if not cos:
        cos = {SYM: json.loads(DATA.read_text())}
    return cos


def company_prices(sym: str, D: dict, C: "Closes", today: dt.date, events: list, ix_on) -> dict:
    """Latest close, series extension, 52w range and return bases for one company."""
    series = {r[0]: list(r[:4]) for r in D["px_series"]}
    w3y_ratio: list = []  # (ex-date, ratio) for corporate actions found through NSE's previous close
    rebased = None
    end = (D.get("co") or {}).get("px_end") or max(series)
    # bonus/split going ex after the snapshot: earlier prices are divided by the ratio
    later = [(ex, r) for ex, r in events if ex > end]
    def fac(day):
        f = 1.0
        for ex, r in later:
            if day < ex:
                f *= r
        return f
    if later:
        series = {k: [k] + [round(v / fac(k), 2) for v in r[1:]] for k, r in series.items()}
    add, stale = [], None
    for k in sorted(C.days):
        v = C.days[k]
        if k <= end or v.get("holiday") or sym not in v.get("eq", {}):
            continue
        c, h, l = v["eq"][sym][:3]
        nse_prev = v["eq"][sym][3] if len(v["eq"][sym]) > 3 else 0
        f = fac(k)
        prior = max((d for d in series if d < k), default=None)
        if prior and nse_prev:
            ours = series[prior][1]  # our previous close, in today's share terms
            ratio = ours / (nse_prev / f)
            if abs(ratio - 1) > 0.01:
                # NSE adjusted its previous close: a split, bonus or demerger went ex today. Re-base history.
                series = {d: [d] + [round(x / ratio, 2) for x in r[1:]] for d, r in series.items()}
                w3y_ratio.append((k, ratio))
        row = [k, round(c / f, 2), round(h / f, 2), round(l / f, 2)]
        series[k] = row
        add = [r for r in add if r[0] < k] + [row]
    rows = [series[k] for k in sorted(series)]
    if w3y_ratio:  # every earlier row changed: ship the whole re-based tail, not just the new days
        add = [r for r in rows if r[0] > end]
        rebased = {"from": end, "ratios": w3y_ratio}
    for a, b in zip(rows, rows[1:]):
        if b[0] > end and abs(b[1] / a[1] - 1) > MAX_JUMP:
            v = C.days.get(b[0], {}).get("eq", {}).get(sym, [])
            if len(v) > 3 and v[3] and abs(v[3] / fac(b[0]) / a[1] - 1) <= 0.01:
                continue  # NSE's own previous close agrees: a genuine price move
            stale = f"{sym} moved {100 * (b[1] / a[1] - 1):.1f}% from {a[0]} to {b[0]} without NSE's previous close explaining it"
            rows = [r for r in rows if r[0] < b[0]]
            add = [r for r in add if r[0] < b[0]]
            break
    now_row, prev_row = rows[-1], rows[-2]
    asof = dt.date.fromisoformat(now_row[0])
    hist = D.get("px_hist") or {}
    rb = 1.0
    for _, r in w3y_ratio:
        rb *= r
    w3y = {d: c / fac(d) / rb for d, c in hist.get("w3y", [])}
    listing = hist.get("listing")

    def close_on(day: dt.date):
        for i in range(10):
            k = (day - dt.timedelta(days=i)).isoformat()
            if k in series:
                return k, series[k][1], round(series[k][1] * factor_raw(k), 2)
            if k in w3y:
                return k, round(w3y[k], 4), None
        return None

    def factor_raw(k):  # adjusted -> raw (only known for ANANDRATHI's own bonus list)
        return factor(k) if sym == SYM else 1.0

    per = [("1m", "1 month", months_back(asof, 1), None), ("3m", "3 months", months_back(asof, 3), None),
           ("6m", "6 months", months_back(asof, 6), None), ("ytd", "Year to date", dt.date(asof.year - 1, 12, 31), None),
           ("1y", "1 year", months_back(asof, 12), None), ("3y", "3 years, annualised", months_back(asof, 36), 3)]
    bases = []
    for k, label, target, yrs in per:
        got = close_on(target)
        if got is None:
            if sym == SYM and k == "3y":  # ANANDRATHI snapshot keeps raw closes back to listing
                raw = {r[0]: r[4] for r in json.loads(BHAV_AR.read_text())}
                for i in range(10):
                    kk = (target - dt.timedelta(days=i)).isoformat()
                    if kk in raw:
                        got = (kk, round(raw[kk] / factor(kk), 4), raw[kk])
                        break
            if got is None:
                continue
        bd, s, sraw = got
        bases.append(dict(k=k, l=label, d=bd, s=s, sraw=sraw if sraw is not None else s, ssrc="NSE bhavcopy", yrs=yrs, **ix_on(bd)))
    if listing or sym == SYM:
        if listing:
            ld, ladj, lraw = listing[0], listing[1] / fac(listing[0]) / rb, listing[2]
        else:
            raw = json.loads(BHAV_AR.read_text())[0]
            ld, lraw = raw[0], raw[4]
            ladj = round(lraw / factor(ld), 4)
        yrs = (asof - dt.date.fromisoformat(ld)).days / 365.25
        if yrs > 0.5:
            bases.append(dict(k="sl", l="Since listing, annualised" if not hist.get("listing_is_first_available") else "Since " + ld[:4] + ", annualised",
                              d=ld, s=round(ladj, 4), sraw=lraw, ssrc="NSE bhavcopy", yrs=yrs, **ix_on(ld)))
    y1 = months_back(asof, 12).isoformat()
    win = [r for r in rows if r[0] > y1]
    hi = max(win, key=lambda r: r[2])
    lo = min(win, key=lambda r: r[3])
    oq_row = [r for r in rows if r[0] <= OPEN_Q_END][-1]
    out = dict(now=dict(d=now_row[0], c=now_row[1], prev=prev_row[1], prevd=prev_row[0]),
               oq=dict(d=oq_row[0], c=oq_row[1], raw=round(oq_row[1] * factor_raw(oq_row[0]), 2), open=asof.isoformat() < OPEN_Q_END),
               add=add, w52=dict(hi=hi[2], hid=hi[0], lo=lo[3], lod=lo[0]), bases=bases)
    if later:
        out["rescale"] = later
    if rebased:
        # share multiplier since the snapshot (e.g. 2.0 after a 1:1 bonus): the app scales share counts with it
        rebased["m"] = round(rb, 6)
        out["rebased"] = rebased
    if stale:
        out["stale"] = stale
    return out


def build(today: dt.date, offline: bool = False) -> dict:
    cos = load_companies()
    univ = {u["sym"]: u for u in json.loads(UNIV.read_text())}
    pxu = json.loads(PXU.read_text()) if PXU.exists() else {}
    for s, u in univ.items():
        pxu.setdefault(s, {"shares": u["shares"], "qbase_close": u.get("close_q2"), "bonus_events": []})
    symbols = set(pxu) | set(cos)
    C = Closes(CACHE, symbols, today, offline)

    # every trading day since the oldest snapshot end, for all symbols (one bhavcopy per day)
    start = min(dt.date.fromisoformat((D.get("co") or {}).get("px_end") or D["px_series"][-1][0]) for D in cos.values())
    d = start + dt.timedelta(days=1)
    while d <= today:
        C.day(d)
        d += dt.timedelta(days=1)
    latest = C.on_or_before(today) or (None, {"eq": {}, "ix": {}})

    bench = (cos.get(SYM) or next(iter(cos.values())))["bench"]
    # Full Nifty 50 / Nifty 500 price history (niftyindices.com) for bases older than NSE's daily index files.
    ih = json.loads(IDX_HIST.read_text()) if IDX_HIST.exists() else {}
    ix_cache: dict[str, dict] = {}
    def ix_on(day: str) -> dict:
        if day not in ix_cache:
            known = {k: bench[n][day] for k, n in (("n50", "nifty50"), ("n500", "nifty500")) if day in bench.get(n, {})}
            for k in ("n50", "n500"):
                if k not in known and day in ih.get(k, {}):
                    known[k] = ih[k][day]
            ih_last = max(max(ih.get("n50", {}) or {"": 0}), max(ih.get("n500", {}) or {"": 0})) if ih else ""
            if len(known) < 2 and not (ih and day <= ih_last):  # the history file already answers every older day
                got = C.day(dt.date.fromisoformat(day))
                known = {**((got or {}).get("ix") or {}), **known}
            out = {"n50": known.get("n50"), "n500": known.get("n500")}
            for k in ("n50", "n500"):  # the index did not exist yet on that day
                first = (ih.get("first") or {}).get(k)
                if out[k] is None and first and day < first:
                    out[k + "_pre"] = first
            ix_cache[day] = out
        return ix_cache[day]

    co_out, stale = {}, []
    for sym, D in cos.items():
        ev = [tuple(e) for e in (pxu.get(sym) or {}).get("bonus_events", [])]
        if sym == SYM:
            ev = [e for e in ev if e[0] > "2026-09-23"]
        try:
            co_out[sym] = company_prices(sym, D, C, today, ev, ix_on)
        except Exception as e:  # one bad company must not block the others
            print(f"warning: {sym}: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        if "stale" in co_out[sym]:
            stale.append(co_out[sym]["stale"])
    for m in stale:
        print("warning:", m, file=sys.stderr)

    asof = max(v["now"]["d"] for v in co_out.values())
    now_ix = ix_on(asof)

    qbase_day = quarter_start(dt.date.fromisoformat(asof)) - dt.timedelta(days=1)
    if qbase_day.isoformat() == "2026-06-30":
        qbase = {s: v.get("qbase_close") for s, v in pxu.items()}
    else:
        got = C.on_or_before(qbase_day)
        qbase = {s: c[0] for s, c in (got[1]["eq"] if got else {}).items()}
    out_u, missing = {}, []
    for s, v in pxu.items():
        px = (latest[1]["eq"].get(s) or [None])[0]
        if px is None:
            missing.append(s)
            continue
        base = qbase.get(s)
        q = round(100 * (px / base - 1), 2) if base else None
        if q is not None and abs(q) > 60 and any(qbase_day.isoformat() < ex <= latest[0].isoformat() for ex, _ in v.get("bonus_events", [])):
            print(f"warning: {s} QTD {q}% spans a split/bonus; shown as n/a", file=sys.stderr)
            q = None
        mult = ((co_out.get(s) or {}).get("rebased") or {}).get("m", 1.0)
        out_u[s] = [px, q, round(v["shares"] * mult * px / 1e7)]
    if missing:
        print(f"note: no {latest[0]} close for {len(missing)} symbols, keeping snapshot prices: {', '.join(sorted(missing)[:8])}", file=sys.stderr)

    C.save()
    return dict(asof=asof, built=dt.datetime.now(IST).isoformat(timespec="minutes"),
                src="NSE bhavcopy and NSE index closes (nsearchives.nseindia.com)",
                stale=bool(C.refused), ix=dict(now=now_ix), co=co_out, univ=out_u,
                qbase=qbase_day.isoformat(), fetched=C.fetched)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--offline", action="store_true", help="use only cache/closes.json")
    ap.add_argument("--today", help="YYYY-MM-DD (default: today in IST)")
    a = ap.parse_args(argv)
    today = dt.date.fromisoformat(a.today) if a.today else dt.datetime.now(IST).date()
    px = build(today, a.offline)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("window.__PX__ = " + json.dumps(px, separators=(",", ":")) + ";\n")
    ar = px["co"].get(SYM, {}).get("now", {})
    print(f"prices.js: as of {px['asof']}; {len(px['co'])} companies; {len(px['univ'])} universe closes; "
          f"{SYM} {ar.get('c')}; Nifty 50 {px['ix']['now']['n50']}; {px['fetched']} NSE days fetched"
          + ("; NSE REFUSED, cache used" if px["stale"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
