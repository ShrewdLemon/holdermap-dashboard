from common import *
import json, os
HERE=os.path.dirname(os.path.abspath(__file__))
U=json.load(open(os.path.join(HERE,"inputs","univ.json")))
for u in U:
    if u['sym']=='ANANDRATHI': u['close']=2169.2; u['mcap_cr']=36018
    u['qtd']=round(100*(u['close']/u['close_q2']-1),2) if u.get('close_q2') else None
U.sort(key=lambda u:-(u.get('mcap_cr') or 0))
univ=[dict(s=u['sym'],n=u['name'],m=u['mcap_cr'],p=u['close'],q=u['qtd'],pr=u.get('prom') or 0,fi=u.get('fii'),di=u.get('dii'),h=u['holders'],fl=u['flagged'],ok=bool(u['passed']),sh=int(u['nholders'] or 0),f=u.get('filing')) for u in U]
tr=[dict(q=t['q'],tot=t['tot'],nh=t['nh'],prom=t['prom'],fii=t['fii'],dii=t['dii'],ind=t['ind'],oth=t['oth'],mf=t['mf'],ins=t['ins'],px=t['close'],bf=t['bonus'],f1=t['f1'],f2=t['f2'],aif=t['aif'],iS=t['iS'],iL=t['iL'],bc=t['bc'],nri=t['nri']) for t in trend]
def H(x,idx5=True):
    return dict(n=x['name'],c=x['cat'],sub=x['sub'],cty=x['cty'],s=x['s'],ow=(x['owner'].split(" · ")[0] if x['owner'] else ""),rv=x['review'],alt=x['alt'])
SUP=[r for r in RUN['rows'] if r['holder']=='Rathi Supriya'][0]
indl=[]
for x in ind:
    d=H(x); d['s']=d['s'][:5]
    if x['name']=='Supriya Saigal': d['s'][0]=SUP['shares'][0]; d['note']='formerly Supriya Rathi'
    if x['name'] in ('Anand Rathi','Pradeep Kumar Gupta','Navratan Mal Gupta'): d['note']='incl. HUF'
    indl.append(d)
def F(f):
    b,s,o=f
    k=lambda x:dict(n=x['name'],c=x['cat'],sub=x['sub'],cty=x['cty'],d=x['d'],v=round(x['val'],2),a=x['after'],b=x['before'],t=x['tag'])
    return dict(buy=[k(x) for x in b],sell=[k(x) for x in s],all=[k(x) for x in o])
flag=[dict(n=nm(r['holder']),c=r['category'],alt=r['alternative'],tier=r['tier'],sh=r['shares'][5] or 0) for r in RUN['rows'] if r['review']]
D=dict(tot=TOT,ff=FF,px=PX,hq=HQ,univ=univ,trend=tr,fii=[H(x) for x in fii],dii=[H(x) for x in dii],ind=indl,
  flows=dict(A=F(f45),B=F(f56)),
  gates=[dict(n=g['name'],d=g['detail']) for g in RUN['gates']],tiers=RUN['tiers'],
  rec=[dict(c=r['category'],b=r['bloomberg_sum'],f=r['filing_total_x_factor'],r=r['ratio'],band=r['band'],note=r['note']) for r in [g for g in RUN['gates'] if g['name']=='category sums vs filing totals'][0]['rows']],
  prices=[dict(q=p['label'],d=p['trade_date'],c=p['close'],f=p['factor'],a=p['adjusted_close'],note=p['note']) for p in RUN['prices']],
  flag=flag, fii_total=10572389, dii_total=17256977, gen=RUN['generated_at'])
s=json.dumps(D,separators=(',',':'),ensure_ascii=False)
open(os.path.join(HERE,"..","src","data.json"),"w").write(s); print(len(s))

# ---- verified price & benchmark layer ----
import prices as P
series=[[s['d'],round(s['c'],2),round(s['h'],2),round(s['l'],2)] for s in P.S if s['d']>='2025-09-01']
anch={}
for d in ['2021-12-14','2023-09-22','2025-09-23','2025-12-31','2026-03-24','2026-06-23','2026-08-21','2026-09-23']:
    b=P.on_or_before(d); anch[d]=[b['d'],round(b['c'],4),b['raw'],P.src.get(b['d'],'NSE bhavcopy')]
D2=json.loads(open(os.path.join(HERE,"..","src","data.json")).read())
D2['px_series']=series
D2['stock_anchor']=anch
D2['bench']=dict(
  nifty50={'2021-12-14':17324.90,'2023-09-22':19674.25,'2025-09-23':25169.50,'2025-12-31':26129.60,'2026-03-24':22912.40,'2026-06-23':23824.10,'2026-08-21':24252.00,'2026-09-23':23446.80},
  nifty500={'2026-08-21':23530.30,'2026-09-23':22935.10},
  override={'nifty500':{'1y':[-1.67,'anandrathi.com/indices/nifty-500, 23 Sep 2026'],'3y':[9.91,'anandrathi.com/indices/nifty-500, 23 Sep 2026 (annualised)']}},
  src={'nifty50':'NSE closes via Business Standard market wraps, Yahoo Finance, Upstox (cross-checked)','nifty500':'investing.com historical data'})
w=[s for s in P.S if s['d']>'2025-09-23']
hi=max(w,key=lambda s:s['h']); lo=min(w,key=lambda s:s['l'])
D2['w52']=dict(hi=round(hi['h'],2),hid=hi['d'],lo=round(lo['l'],2),lod=lo['d'])
D2['earn']=dict(q=['Q4 FY25','Q1 FY26','Q2 FY26','Q3 FY26','Q4 FY26','Q1 FY27'],d=['Mar-25','Jun-25','Sep-25','Dec-25','Mar-26','Jun-26'],
  rev=[221.96,274.02,297.4,289.6,287.82,321.99],pat=[73.74,93.9,99.9,100.1,103.45,163.0],
  eps_rep=[8.87,11.31,12.0,12.06,12.5,9.82],sh_basis=['83.02 mn','83.02 mn','83.02 mn','83.02 mn','83.02 mn','166.04 mn'])
open(os.path.join(HERE,"..","src","data.json"),"w").write(json.dumps(D2,separators=(',',':'),ensure_ascii=False))
print('anch',anch); print('w52',D2['w52'])
