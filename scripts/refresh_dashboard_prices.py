#!/usr/bin/env python3
"""Top up the dashboard's benchmark closes (dashboard/site/data.js) from yfinance.

data.js has the form `window.__HM__ = {...};`. Downloaded closes are MERGED into
bench.nifty50 / bench.nifty500: existing values are never deleted or overwritten;
only missing dates are filled. A present value that differs by >0.5% is reported
and kept. Optional: exits 0 with a hint when yfinance is not installed.
"""
import datetime as dt
import json
import sys
from pathlib import Path

DATA_JS = Path(__file__).resolve().parent.parent / "dashboard" / "site" / "data.js"
START = "2021-12-01"
BENCH = {"nifty50": "^NSEI", "nifty500": "^CRSLDX"}
EXTRA = ["ANANDRATHI.NS"]
TOL = 0.005


def closes(yf, ticker, start, end):
    """Return {YYYY-MM-DD: close} for one ticker (handles MultiIndex columns)."""
    df = yf.download(ticker, start=start, end=end, interval="1d",
                     auto_adjust=False, progress=False)
    if df is None or len(df) == 0:
        return {}
    if getattr(df.columns, "nlevels", 1) > 1:
        lvl0 = df.columns.get_level_values(0)
        col = df["Close"] if "Close" in lvl0 else df.xs("Close", axis=1, level=1)
        if getattr(col, "ndim", 1) > 1:
            col = col[ticker] if ticker in col.columns else col.iloc[:, 0]
    else:
        col = df["Close"]
    result = {}
    for idx, v in col.dropna().items():
        result[idx.strftime("%Y-%m-%d")] = round(float(v), 2)
    return result


def main():
    try:
        import yfinance as yf
    except ImportError:
        print("refresh_dashboard_prices: yfinance not installed; skipping "
              "(pip install yfinance)")
        return 0
    if not DATA_JS.exists():
        print(f"refresh_dashboard_prices: {DATA_JS} not found; skipping")
        return 0

    text = DATA_JS.read_text(encoding="utf-8")
    head, sep, rest = text.partition("=")
    body = rest.strip()
    if not sep or not body.endswith(";"):
        print("refresh_dashboard_prices: unexpected data.js format", file=sys.stderr)
        return 1
    data = json.loads(body[:-1])
    bench = data.setdefault("bench", {})

    end = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    for key, ticker in BENCH.items():
        got = closes(yf, ticker, START, end)
        series = bench.setdefault(key, {})
        added = 0
        for day, px in sorted(got.items()):
            if day not in series:
                series[day] = px
                added += 1
            else:
                old = series[day]
                if old and abs(px - old) / abs(old) > TOL:
                    print(f"warning: {key} {day}: existing {old} vs yfinance {px} "
                          f"(>{TOL:.1%}); keeping existing")
        bench[key] = dict(sorted(series.items()))
        print(f"{key} ({ticker}): {len(got)} downloaded, {added} added, "
              f"{len(series)} total")

    for ticker in EXTRA:
        got = closes(yf, ticker, START, end)
        last = max(got) if got else None
        print(f"{ticker}: {len(got)} closes downloaded"
              + (f", last {last} = {got[last]}" if last else ""))

    bench["refreshed"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    bench["source_refresh"] = "yfinance"
    DATA_JS.write_text(head.rstrip() + " = "
                       + json.dumps(data, separators=(",", ":"), ensure_ascii=False)
                       + ";\n", encoding="utf-8")
    print(f"wrote {DATA_JS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
