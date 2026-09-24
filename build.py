"""Assemble the dashboard from src/ into dashboard/site (for S3/CloudFront) and dashboard/standalone.html.

    python3 pipeline/export.py   # optional: rebuild src/data.json from pipeline/inputs
    python3 pipeline/live.py     # optional: latest NSE closes -> dashboard/site/prices.js
    python3 build.py

Without prices.js the page shows the snapshot's own prices from data.json.
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
assert "</script" not in univ
(site / "data.js").write_text("window.__UNIV__ = " + univ + ";\n")
co_dir = site / "co"
co_dir.mkdir(exist_ok=True)
for old in co_dir.glob("*.js"):
    old.unlink()
cos = {f.stem: f.read_text() for f in sorted((src / "co").glob("*.json"))} if (src / "co").exists() else {}
cos.setdefault("ANANDRATHI", data)
for sym, cjson in cos.items():
    assert "</script" not in cjson
    (co_dir / f"{sym}.js").write_text(f"(window.__CO__=window.__CO__||{{}})[{json.dumps(sym)}]=" + cjson + ";\n")
ar = cos["ANANDRATHI"]
prices = site / "prices.js"
if not prices.exists():
    prices.write_text("window.__PX__ = null;\n")
px = prices.read_text()
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
