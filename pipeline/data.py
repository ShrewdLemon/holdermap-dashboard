import json, glob, collections, re, xml.etree.ElementTree as ET
import os
X=os.path.join(os.path.dirname(os.path.abspath(__file__)),"inputs","xbrl")+"/"
FIL=["2025-03-31","2025-06-30","2025-09-30","2025-12-31","2026-03-31","2026-06-30"]
QL=["Mar-25","Jun-25","Sep-25","Dec-25","Mar-26","Jun-26"]
CLOSE=[1912.2,2159.7,2826.8,3112.4,3035.4,1976.7]
BONUS=[2,2,2,2,2,1]
def facts(f):
    d=collections.defaultdict(dict)
    for el in ET.parse(f).getroot():
        t=el.tag.split('}')[-1]
        if el.get('contextRef') and t in ('NumberOfShares','NumberOfShareholders'):
            d[el.get('contextRef')][t]=el.text
    def g(k):
        for cid in (k+'_ContextI',k+'I'):
            if cid in d: return int(float(d[cid]['NumberOfShares'])), int(float(d[cid].get('NumberOfShareholders') or 0))
        # older naming for small individuals
        for cid in d:
            if cid.startswith(k): return int(float(d[cid]['NumberOfShares'])), int(float(d[cid].get('NumberOfShareholders') or 0))
        return 0,0
    return g
trend=[]
for i,f in enumerate(FIL):
    g=facts(X+f+".xml")
    tot,nh=g('ShareholdingPattern')
    prom=g('ShareholdingOfPromoterAndPromoterGroup')[0]
    fii=g('InstitutionsForeign')[0]; dii=g('InstitutionsDomestic')[0]
    ind=g('ResidentIndividualShareholdersHoldingNominalShareCapitalUpToRsTwoLakh')[0]+g('ResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh')[0]
    mf=g('MutualFundsOrUTI')[0] or g('MutualFundsOrUti')[0]
    ins=g('InsuranceCompanies')[0]
    oth=tot-prom-fii-dii-ind
    f1=g('InstitutionsForeignPortfolioInvestorCategoryOne')[0] or g('InstitutionsForeignPortfolioInvestorCatergoryOne')[0]
    f2=g('InstitutionsForeignPortfolioInvestorCategoryTwo')[0] or g('InstitutionsForeignPortfolioInvestorCatergoryTwo')[0]
    aif=g('AlternativeInvestmentFunds')[0]
    iS=g('ResidentIndividualShareholdersHoldingNominalShareCapitalUpToRsTwoLakh')[0]; iL=g('ResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh')[0]
    bc=g('BodiesCorporate')[0]; nri=g('NonResidentIndians')[0]
    trend.append(dict(q=QL[i],tot=tot,nh=nh,prom=prom,fii=fii,dii=dii,ind=ind,oth=oth,mf=mf,ins=ins,close=CLOSE[i],bonus=BONUS[i],f1=f1,f2=f2,aif=aif,iS=iS,iL=iL,bc=bc,nri=nri))
if __name__=="__main__":
    for t in trend:
        T=t['tot']; print(t['q'],T,t['nh'],*[round(100*t[k]/T,2) for k in ('prom','fii','dii','ind','oth','mf','ins')], round(T*t['close']/1e7))

RUN=json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),"inputs","run.json")))
TOT=166041268
PROM_R=[70927164,70927164,71587164,71587164,68695158,68695158]
FF=[TOT-p for p in PROM_R]
PX=[p['adjusted_close'] for p in RUN['prices']]  # restated-basis price per quarter
PX[5]=2169.2  # latest close 23-Sep-2026
HQ=["Jun-25","Sep-25","Dec-25","Mar-26","Jun-26","Sep-26"]
COUNTRY={'Vanguard Group Inc/The':'US','Blackrock Inc':'US','Norges Bank':'NO','American Century Cos Inc':'US','Goldman Sachs Group Inc/The':'US','WBC Holdings LP':'US','Victory Capital Management Inc':'US','Driehaus Capital Management LLC':'US','WisdomTree Inc':'US','Teachers Insurance & Annuity Association of America':'US','State Street Corp':'US','FMR LLC':'US','AllianceBernstein Holding LP':'US','National Bank of Canada':'CA','Thrivent Financial for Lutherans':'US','Taiwan Securities Co Ltd':'TW','Nomura Holdings Inc':'JP','Nationwide Fund Advisors':'US','Legal & General Group PLC':'GB','Franklin Templeton Inc':'US','FlexShares Trust':'US','Canadian Imperial Bank of Commerce':'CA','Credit Agricole Group':'FR','Deutsche Bank AG':'DE','Prudential Financial Inc':'US','FIL Ltd':'BM','Russell Investments Group Ltd':'US','JPMorgan Chase & Co':'US','Sun Life Financial Inc':'CA','Wilshire Advisors LLC':'US'}
SUB={'Foreign AMC':'Asset manager','Foreign Government':'Central bank','Foreign Insurance':'Insurer','Foreign corporate':'Holding co.','Bank':'Bank group','Domestic AMC':'Mutual fund','Domestic Insurance':'Life insurer','Promoter':'Promoter group','Individual':'Public','Domestic corporate':'Corporate'}
NICE={'Vanguard Group Inc/The':'The Vanguard Group','Blackrock Inc':'BlackRock','Goldman Sachs Group Inc/The':'Goldman Sachs Group','Teachers Insurance & Annuity Association of America':'TIAA (Nuveen)','AXIS MAX LIFE INSURANCE LTD':'Axis Max Life Insurance','SAMCO ASSET MANAGEMENT INDIA':'Samco Asset Management','CAPITALMIND ASSET MANAGEMENT':'Capitalmind Asset Management','ALPHAGREP INVESTMENT MGMT INDIA':'AlphaGrep Investment Mgmt','JAIPUR SECURITIES PVT LTD':'Jaipur Securities Pvt Ltd','SUHAS GUPTA FAMILY TRUST':'Suhas Gupta Family Trust','Canara Robeco Asset Management Co Ltd/India':'Canara Robeco AMC','ICICI Prudential Asset Management Co Ltd/India':'ICICI Prudential AMC','Kotak Mahindra Asset Management Co Ltd/India':'Kotak Mahindra AMC','Axis Asset Management Co Ltd/India':'Axis AMC','Union Mutual Fund/India':'Union Mutual Fund','Motilal Oswal Asset Management Co Ltd':'Motilal Oswal AMC','Aditya Birla Sun Life Asset Management Co Ltd':'Aditya Birla Sun Life AMC','Bank of India Investment Managers Pvt Ltd':'Bank of India Investment Mgrs','Nippon Life India Asset Management Ltd':'Nippon Life India AMC','Invesco Asset Management India Pvt Ltd':'Invesco AMC (India)','Star Union Dai-Ichi Life Insurance Co Ltd':'Star Union Dai-ichi Life','ICICI Prudential Life Insurance Co Ltd':'ICICI Prudential Life','Aditya Birla Sun Life Insurance Co Ltd':'Aditya Birla Sun Life Insurance','Gupta Pradeep Kumar':'Pradeep Kumar Gupta','Gupta Priti':'Priti Gupta','Gupta Navratan Mal':'Navratan Mal Gupta','Maru Pooja':'Pooja Maru','Mantri Tara':'Tara Mantri','Gupta Krishnav Pradeep':'Krishnav Pradeep Gupta','Mundra Phool Kaur':'Phool Kaur Mundra','Biyani Asha Kailash':'Asha Kailash Biyani','Gupta Aishwariya P':'Aishwariya P Gupta','Azeez Feroze':'Feroze Azeez','Rathi Amit':'Amit Rathi','Saigal Supriya':'Supriya Saigal','Ali Fahim Sultan':'Fahim Sultan Ali','Rawal Rakesh':'Rakesh Rawal','Rawal Preeti':'Preeti Rawal','Rathi Suresh':'Suresh Rathi','Taiwan Securities Co Ltd':'Taiwan Securities (Taishin)','Anand Rathi':'Anand Rathi'}
def nm(h): return NICE.get(h,h)
def sh(r,i):
    v=r['shares'][i]; return v or 0
rows=RUN['rows']
FOREIGN={'Foreign AMC','Foreign Government','Foreign Insurance','Foreign corporate','Bank'}
DOM={'Domestic AMC','Domestic Insurance','Domestic Pension Fund','Government'}
def holder_rec(r, idx=5, basis_ff=True):
    s=[sh(r,i) for i in range(6)]
    pt=[100*s[i]/TOT for i in range(6)]
    return dict(name=nm(r['holder']),raw=r['holder'],cat=r['category'],sub=SUB.get(r['category'],r['category']),cty=COUNTRY.get(r['holder'],'IN'),
        s=s,pt=pt,pff=[100*s[i]/FF[i] for i in range(6)],val=s[idx]*PX[idx]/1e7,
        mean=sum(pt)/6,mx=max(pt),mn=min(pt),owner=r.get('owner',''),review=r['review'],tier=r['tier'],alt=r['alternative'])
fii=sorted([holder_rec(r) for r in rows if r['category'] in FOREIGN and sh(r,5)>0],key=lambda x:-x['s'][5])[:20]
dii=sorted([holder_rec(r) for r in rows if r['category'] in DOM and sh(r,5)>0],key=lambda x:-x['s'][5])[:20]
IND_EXCL={'Rathi Supriya','Rawal Preeti','Rawal Rakesh','Rawal Family Trust','Rathi Suresh'}
ind=sorted([holder_rec(r,4) for r in rows if (r['category']=='Individual' or (r['category']=='Promoter' and not re.search(r'(Ltd|LTD|Pvt|PVT)',r['holder']))) and r['holder'] not in IND_EXCL and sh(r,4)>0],key=lambda x:-x['s'][4])[:20]
# coverage
fii_cov=sum(sh(r,4) for r in rows if r['category'] in FOREIGN)/10572389
dii_cov=sum(sh(r,4) for r in rows if r['category'] in DOM)/17256977
STALE={'Rathi Amit','Rathi Supriya','Saigal Supriya','Ali Fahim Sultan','Rawal Rakesh','Rawal Preeti','Rawal Family Trust','SUHAS GUPTA FAMILY TRUST','Munix India Pvt Ltd','Rathi Suresh'}
def flows(a,b,excl=set()):
    out=[]
    for r in rows:
        if r['holder'] in excl or r['holder']=='ANANDRATHI HOUSING FIN LTD' or r['holder']=='Rathi Supriya': continue
        d=sh(r,b)-sh(r,a)
        if d==0: continue
        tag='New' if sh(r,a)==0 and sh(r,b)>0 else ('Exit' if sh(r,b)==0 else '')
        out.append(dict(name=nm(r['holder']),cat=r['category'],sub=SUB.get(r['category'],r['category']),cty=COUNTRY.get(r['holder'],'IN'),d=d,val=d*PX[b]/1e7,pp=100*d/TOT,before=sh(r,a),after=sh(r,b),tag=tag,chg=(100*d/sh(r,a) if sh(r,a) else None)))
    buy=sorted([o for o in out if o['d']>0],key=lambda o:-o['d'])[:25]
    sell=sorted([o for o in out if o['d']<0],key=lambda o:o['d'])[:25]
    return buy,sell,out
f45=flows(3,4); f56=flows(4,5,STALE)
if __name__=="__main__":
    print("FII cov",fii_cov,"DII cov",dii_cov)
    for L,n in ((fii,'FII'),(dii,'DII'),(ind,'IND')):
        print("==",n,len(L))
        for x in L: print(f"  {x['name'][:34]:34} {x['cty']} {x['sub']:13} {x['s'][5]:>10} {x['pt'][5]:.3f} {x['pff'][5]:.3f} {x['val']:.1f} m{x['mean']:.3f} {x['mx']:.3f} {x['mn']:.3f}")
    for f,n in ((f45,'Q4->Q5'),(f56,'Q5->Q6')):
        b,s,o=f; print("==",n,len(b),len(s))
        for x in b[:25]: print("  B",f"{x['name'][:32]:32}",x['d'],round(x['val'],1),x['tag'])
        for x in s[:25]: print("  S",f"{x['name'][:32]:32}",x['d'],round(x['val'],1),x['tag'])
