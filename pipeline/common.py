import html
from data import *
INK="#15171C"; INK2="#4A505C"; INK3="#646B78"; RULE="#E4E1DA"; BG="#F4F3EF"; PANEL="#FFFFFF"; ACC="#B8321C"
UP="#1B7346"; DN="#B42318"
C={'prom':'#1B2F4E','fii':'#D9782D','dii':'#4F86C6','ind':'#A9B6C6','oth':'#D9D5CB'}
LBL={'prom':'Promoter & group','fii':'FII / FPI','dii':'DII','ind':'Individuals','oth':'Others'}
def e(s): return html.escape(str(s),quote=True)
def fin(n,dec=0):
    neg=n<0; n=abs(n)
    s=f"{n:.{dec}f}"; ip,_,fp=s.partition('.')
    if len(ip)>3:
        head,tail=ip[:-3],ip[-3:]
        parts=[]
        while len(head)>2: parts.insert(0,head[-2:]); head=head[:-2]
        if head: parts.insert(0,head)
        ip=",".join(parts+[tail])
    return ("−" if neg else "")+ip+("."+fp if fp else "")
def sgn(x,dec=2,suf=""):
    if x is None: return "—"
    s=f"{abs(x):.{dec}f}{suf}"
    return ("+" if x>0 else "−" if x<0 else "")+s
def colr(x): return UP if (x or 0)>0 else DN if (x or 0)<0 else INK3
def spark(vals,w=96,h=24,color=INK,fill=None,dot=True):
    lo,hi=min(vals),max(vals); rng=(hi-lo) or 1
    pts=[(2+i*(w-4)/(len(vals)-1), h-3-(v-lo)/rng*(h-6)) for i,v in enumerate(vals)]
    p=" ".join(f"{x:.1f},{y:.1f}" for x,y in pts)
    a=f'<polygon points="{pts[0][0]:.1f},{h} {p} {pts[-1][0]:.1f},{h}" fill="{fill}" stroke="none"></polygon>' if fill else ""
    d=f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="2.5" fill="{color}"></circle>' if dot else ""
    return f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" aria-hidden="true" style="display: block">{a}<polyline points="{p}" fill="none" stroke="{color}" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"></polyline>{d}</svg>'
FONTS='<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&amp;family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400&amp;family=Source+Serif+4:opsz,wght@8..60,500;8..60,600&amp;display=swap" rel="stylesheet">'
CSS=f"""
body{{margin:0;background:{BG};font-family:'IBM Plex Sans',system-ui,sans-serif;color:{INK};-webkit-font-smoothing:antialiased}}
a{{color:{INK};text-decoration:none}} a:hover{{color:{ACC}}}
.serif{{font-family:'Source Serif 4',Georgia,serif}}
.mono{{font-family:'IBM Plex Mono',ui-monospace,monospace}}
.t{{border-collapse:collapse;width:100%}}
.t th{{font-size:11px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;color:{INK3};text-align:right;padding:10px 10px 8px;border-bottom:1.5px solid {INK};white-space:nowrap}}
.t td{{font-size:13px;padding:9px 10px;border-bottom:1px solid {RULE};text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
.t .l{{text-align:left}}
.t tr:hover td{{background:#FAF8F3}}
.t tr.sub td{{color:{INK3};font-size:12px;padding-top:5px;padding-bottom:5px}}
.t tr.tot td{{font-weight:600;border-top:1.5px solid {INK};border-bottom:none}}
.vh{{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}}
input::placeholder{{color:#9097A3}}
"""
def page(title,body,props,script,w,h):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{e(title)}</title>
<script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
{FONTS}
<style>{CSS}</style>
</helmet>
<div style="width: {w}px; height: {h}px; background: {BG}; display: flex; flex-direction: column; overflow: hidden">
{body}
</div>
</x-dc>
<script type="text/x-dc" data-dc-script data-props='{props}'>
{script}
</script>
</body>
</html>
"""
def appbar(active):
    nav=""
    for lab,href in (("Universe","Universe.dc.html"),("Company","Main.dc.html"),("Screens",None),("Watchlist",None)):
        on=lab==active
        st=f"font-size: 13px; font-weight: 500; color: {'#FFFFFF' if on else '#B9BEC8'}; padding: 18px 0 15px; border-bottom: 3px solid {ACC if on else 'transparent'}"
        nav+= f'<a href="{href}" style="{st}">{lab}</a>' if href else f'<a href="#" style="{st}">{lab}</a>'
    return f"""<header style="height: 56px; flex-shrink: 0; background: {INK}; display: flex; align-items: center; gap: 36px; padding: 0 40px; box-sizing: border-box">
<a href="Universe.dc.html" style="display: flex; align-items: center; gap: 10px; color: #FFFFFF">
<svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true"><rect x="1" y="1" width="9" height="9" fill="{ACC}"></rect><rect x="12" y="1" width="9" height="9" fill="none" stroke="#FFFFFF" stroke-width="1.5"></rect><rect x="1" y="12" width="9" height="9" fill="none" stroke="#FFFFFF" stroke-width="1.5"></rect><rect x="12" y="12" width="9" height="9" fill="#FFFFFF"></rect></svg>
<span class="serif" style="font-size: 20px; font-weight: 600; letter-spacing: -0.01em">holdermap</span>
</a>
<nav aria-label="Primary" style="display: flex; gap: 28px; align-self: stretch; align-items: flex-end">{nav}</nav>
<div style="flex-grow: 1; display: flex; justify-content: center">
<label for="gsearch" class="vh">Search</label>
<div style="width: 420px; height: 36px; display: flex; align-items: center; gap: 10px; padding: 0 12px; background: #262931; border: 1px solid #3A3E48; box-sizing: border-box">
<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#9097A3" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><path d="M20 20l-4-4"></path></svg>
<input id="gsearch" type="search" placeholder="Search company, ISIN or holder" style="flex-grow: 1; background: transparent; border: none; outline: none; color: #FFFFFF; font-family: inherit; font-size: 13px">
<span class="mono" style="font-size: 11px; color: #9097A3; border: 1px solid #3A3E48; padding: 1px 6px">/</span>
</div>
</div>
<span style="font-size: 12px; color: #B9BEC8">Prices · NSE close 23 Sep 2026</span>
<button aria-label="Account" style="width: 32px; height: 32px; border-radius: 16px; border: none; background: #3A3E48; color: #FFFFFF; font-family: inherit; font-size: 12px; font-weight: 600; cursor: pointer">PP</button>
</header>"""
PRICES=[956.1,1079.85,1413.4,1556.2,1517.7,1976.7,2073.7,2204.2,2169.2]
def company_header(active):
    stats=[("Market cap","₹36,018 cr",""),("P/E (TTM)","77.3×","Core ex-MTM 86.0×"),("P/B","36.1×","BVPS ₹60.1"),("Dividend yield","0.30%","FY26 DPS ₹6.50 adj."),("ROE","47.3%","ROCE 59.2%"),("Free float","58.63%","Jun-26 filing"),("Shareholders","80,729","+24.3% QoQ")]
    cells="".join(f'<div style="display: flex; flex-direction: column; gap: 3px; padding: 0 20px; border-left: 1px solid {RULE}"><span style="font-size: 11px; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; color: {INK3}">{a}</span><span style="font-size: 17px; font-weight: 600; font-variant-numeric: tabular-nums">{b}</span><span style="font-size: 11px; color: {INK3}">{c or "&#160;"}</span></div>' for a,b,c in stats)
    # 52w range
    lo,hi,cur=1354,2268,2169.2; pos=(cur-lo)/(hi-lo)*100
    rng=f'<div style="display: flex; flex-direction: column; gap: 6px; padding: 0 20px; border-left: 1px solid {RULE}; width: 200px"><span style="font-size: 11px; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; color: {INK3}">52-week range</span><div style="position: relative; height: 4px; background: {RULE}; margin-top: 8px"><div style="position: absolute; left: 0; top: 0; height: 4px; width: {pos:.1f}%; background: {INK}"></div><div style="position: absolute; left: {pos:.1f}%; top: -5px; width: 2px; height: 14px; background: {ACC}"></div></div><div style="display: flex; justify-content: space-between; font-size: 11px; color: {INK3}; font-variant-numeric: tabular-nums"><span>1,354</span><span>2,268</span></div></div>'
    tabs=""
    for lab,href in (("Overview","Main.dc.html"),("Shareholding","Holders.dc.html"),("Buyers &amp; sellers","Flows.dc.html"),("Evidence &amp; gates","Evidence.dc.html")):
        on=href==active
        tabs+=f'<a href="{href}" style="font-size: 14px; font-weight: {600 if on else 500}; color: {INK if on else INK2}; padding: 14px 0 12px; border-bottom: 3px solid {ACC if on else "transparent"}">{lab}</a>'
    chip=lambda t: f'<span class="mono" style="font-size: 11px; color: {INK2}; border: 1px solid {RULE}; padding: 2px 7px; background: #FAF9F6">{t}</span>'
    return f"""<section aria-label="Company summary" style="background: {PANEL}; border-bottom: 1px solid {RULE}; padding: 20px 40px 0; display: flex; flex-direction: column; gap: 18px; flex-shrink: 0">
<div style="font-size: 12px; color: {INK3}; display: flex; gap: 8px"><a href="Universe.dc.html" style="color: {INK3}">Universe</a><span>/</span><span>Financial Services</span><span>/</span><span style="color: {INK}">ANANDRATHI</span></div>
<div style="display: flex; justify-content: space-between; align-items: flex-end; gap: 32px">
<div style="display: flex; flex-direction: column; gap: 10px">
<h1 class="serif" style="margin: 0; font-size: 36px; font-weight: 600; letter-spacing: -0.015em; line-height: 1.1">Anand Rathi Wealth Ltd</h1>
<div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap">{chip("NSE: ANANDRATHI")}{chip("BSE: 543415")}{chip("ISIN INE463V01026")}<span style="font-size: 12px; color: {INK2}; padding-left: 6px">Capital Markets · Financial Products Distributor</span><span style="font-size: 11px; font-weight: 600; color: #FFFFFF; background: {INK}; padding: 3px 8px; letter-spacing: 0.04em">MID CAP</span><span style="font-size: 11px; font-weight: 600; color: {UP}; border: 1px solid {UP}; padding: 2px 8px">7/7 GATES PASSED</span></div>
</div>
<div style="display: flex; align-items: flex-end; gap: 24px">
<div style="display: flex; flex-direction: column; gap: 4px; align-items: flex-end">
<span style="font-size: 11px; color: {INK3}">Quarter-end closes, bonus-adjusted · Mar-25 → 23 Sep 26</span>
{spark(PRICES,200,44,INK,"#EEF0F3")}
</div>
<div style="display: flex; flex-direction: column; align-items: flex-end; gap: 2px">
<span style="font-size: 34px; font-weight: 600; font-variant-numeric: tabular-nums; letter-spacing: -0.01em">₹2,169.20</span>
<span style="font-size: 14px; font-weight: 600; color: {DN}; font-variant-numeric: tabular-nums">−9.80 (−0.45%)</span>
<span style="font-size: 11px; color: {INK3}">NSE close · 23 Sep 2026</span>
</div>
</div>
</div>
<div style="display: flex; align-items: stretch; padding: 14px 0; border-top: 1px solid {RULE}; margin-left: -20px">{cells}{rng}</div>
<nav aria-label="Company sections" style="display: flex; gap: 32px; border-top: 1px solid {RULE}">{tabs}</nav>
</section>"""
def sec_head(num,title,sub="",right=""):
    return f"""<div style="display: flex; justify-content: space-between; align-items: flex-end; gap: 16px; padding-bottom: 12px; border-bottom: 2px solid {INK}">
<div style="display: flex; flex-direction: column; gap: 4px">
<span class="mono" style="font-size: 11px; color: {ACC}; letter-spacing: 0.06em">{num}</span>
<h2 class="serif" style="margin: 0; font-size: 22px; font-weight: 600; letter-spacing: -0.01em">{title}</h2>
{f'<span style="font-size: 12px; color: {INK3}">{sub}</span>' if sub else ''}
</div>
{right}
</div>"""
def card(inner,span=12,pad=24):
    return f'<section style="grid-column: span {span} / span {span}; background: {PANEL}; border: 1px solid {RULE}; padding: {pad}px; display: flex; flex-direction: column; gap: 18px; box-sizing: border-box">{inner}</section>'
def swatch(k): return f'<span style="display: inline-block; width: 10px; height: 10px; background: {C[k]}; margin-right: 8px; vertical-align: -1px"></span>'
def cty_chip(c): return f'<span class="mono" style="font-size: 11px; color: {INK2}; border: 1px solid {RULE}; padding: 1px 5px">{c}</span>'
def sub_chip(s): return f'<span style="font-size: 11px; color: {INK3}; margin-left: 8px">{e(s)}</span>'
def footer(txt):
    return f'<footer style="padding: 20px 40px 28px; font-size: 11px; line-height: 1.6; color: {INK3}; flex-shrink: 0">{txt}</footer>'
