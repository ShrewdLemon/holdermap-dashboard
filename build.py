"""Assemble the dashboard from src/ into dashboard/site (for S3/CloudFront) and dashboard/standalone.html.

    python3 pipeline/live.py     # latest NSE/BSE closes -> dashboard/prices_full.json (optional)
    python3 build.py

Writes data.js (the universe: src/univ.json + src/univ_extra.json), co/<SYM>.js for every company in src/co/
(each with its own live price block from prices_full.json), a small shared prices.js (as-of date, index
closes, universe prices) and index.html. Without prices_full.json the pages use each snapshot's own prices.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
src = ROOT / "src"
head = (src / "head.html").read_text()
body = (src / "body.html").read_text()
js = (src / "app.js").read_text()
data = (src / "data.json").read_text()
assert "</script" not in data

site = ROOT / "dashboard" / "site"
site.mkdir(parents=True, exist_ok=True)
css = re.search(r"<style>(.*)</style>", head, re.S).group(1)
links = "\n".join(re.findall(r"<link[^>]+>", head))
(site / "app.css").write_text(css)
(site / "app.js").write_text(js)
# Universe (every company row) and one data file per company, loaded on demand by app.js.
import json
univ_src = src / "univ.json"
univ = univ_src.read_text() if univ_src.exists() else json.dumps(json.loads(data)["univ"], separators=(",", ":"))
extra_src = src / "univ_extra.json"  # companies outside the index universe (pipeline/extra_*.py)
if extra_src.exists():
    rows = json.loads(univ)
    have = {r["s"] for r in rows}
    univ = json.dumps(rows + [r for r in json.loads(extra_src.read_text()) if r["s"] not in have], separators=(",", ":"))
assert "</script" not in univ
(site / "data.js").write_text("window.__UNIV__ = " + univ + ";\n")
co_dir = site / "co"
co_dir.mkdir(exist_ok=True)
for old in co_dir.glob("*.js"):
    old.unlink()
cos = {f.stem: f.read_text() for f in sorted((src / "co").glob("*.json"))} if (src / "co").exists() else {}
cos.setdefault("ANANDRATHI", data)
# Live prices (pipeline/live.py) are per company: each company's block rides in its own file, so the shared
# prices.js stays small (asof, index closes, universe prices) however large the universe gets.
prices_path = site / "prices.js"
full_path = ROOT / "dashboard" / "prices_full.json"  # written by pipeline/live.py
px_all = json.loads(full_path.read_text()) if full_path.exists() else None
for sym, cjson in cos.items():
    assert "</script" not in cjson
    live = json.dumps((px_all or {}).get("co", {}).get(sym), separators=(",", ":")) if px_all else "null"
    (co_dir / f"{sym}.js").write_text(f"(window.__CO__=window.__CO__||{{}})[{json.dumps(sym)}]=" + cjson + ";"
                                      + f"window.__CO__[{json.dumps(sym)}].live=" + live + ";\n")
slim = {k: v for k, v in (px_all or {}).items() if k != "co"} if px_all else None
prices_path.write_text("window.__PX__ = " + json.dumps(slim, separators=(",", ":")) + ";\n")
ar = cos["ANANDRATHI"][:-1] + ',"live":' + (json.dumps(px_all["co"].get("ANANDRATHI")) if px_all else "null") + "}"
px = prices_path.read_text()
assert "</script" not in px
(site / "index.html").write_text(f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex,nofollow">
<title>holdermap</title>
{links}
<link rel="stylesheet" href="app.css">
<style>:root{{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}}body{{margin:0}}[hidden]{{display:none!important}}img{{max-width:100%}}</style>
</head>
<body>
{body}
<script src="data.js"></script>
<script src="prices.js"></script>
<script src="app.js"></script>
</body>
</html>
""")
(ROOT / "dashboard" / "standalone.html").write_text(
    head + "\n" + body + "\n<script>window.__UNIV__=" + univ + ";window.__CO__={ANANDRATHI:" + ar + "};</script>\n<script>" + px + "</script>\n<script>\n" + js + "</script>\n")
print("built", site, f"({len(cos)} company dashboards) and dashboard/standalone.html")
