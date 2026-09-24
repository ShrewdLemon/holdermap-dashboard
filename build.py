"""Assemble the dashboard from src/ into dashboard/site (for S3/CloudFront) and dashboard/standalone.html.

    python3 pipeline/export.py   # optional: rebuild src/data.json from pipeline/inputs
    python3 build.py
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
(site / "data.js").write_text("window.__HM__ = " + data + ";\n")
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
<script src="app.js"></script>
</body>
</html>
""")
(ROOT / "dashboard" / "standalone.html").write_text(
    head + "\n" + body + "\n<script>window.__HM__=" + data + ";</script>\n<script>\n" + js + "</script>\n")
print("built", site, "and dashboard/standalone.html")
