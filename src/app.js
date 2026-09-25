(function(){
"use strict";
let D = null;  // the company on screen (co/<SYM>.js), set by setCompany()
window.__CO__ = window.__CO__ || {};
if (window.__HM__ && !window.__CO__.ANANDRATHI) window.__CO__.ANANDRATHI = window.__HM__;
const U = window.__UNIV__ || (window.__HM__ ? window.__HM__.univ : []);  // the stock universe
const DASH = new Set(U.filter(u => u.dash).map(u => u.s).concat(Object.keys(window.__CO__)));
const $ = (s, r) => (r || document).querySelector(s);
const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
const store = {
  get(k, d) { try { const v = localStorage.getItem('hm.' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem('hm.' + k, JSON.stringify(v)); } catch (e) {} }
};
const RM = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/* ---------- formatting ---------- */
function fin(n, d) {
  d = d || 0; if (n == null || isNaN(n)) return '—';
  const neg = n < 0; n = Math.abs(n);
  let parts = n.toFixed(d).split('.'), i = parts[0], f = parts[1];
  if (i.length > 3) { let h = i.slice(0, -3), t = i.slice(-3), p = []; while (h.length > 2) { p.unshift(h.slice(-2)); h = h.slice(0, -2); } if (h) p.unshift(h); i = p.join(',') + ',' + t; }
  return (neg ? '−' : '') + i + (f ? '.' + f : '');
}
const sgn = (x, d, suf) => (x == null || isNaN(x)) ? '—' : (x > 0 ? '+' : x < 0 ? '−' : '') + Math.abs(x).toFixed(d == null ? 2 : d) + (suf || '');
const sgnI = (x) => x == null ? '—' : (x > 0 ? '+' : x < 0 ? '−' : '') + fin(Math.abs(x));
const sgnC = (x, d) => x == null || isNaN(x) ? '—' : (x > 0 ? '+' : x < 0 ? '−' : '') + fin(Math.abs(x), d == null ? 1 : d);  // signed, Indian grouping
const cl = x => x > 0 ? 'up' : x < 0 ? 'dn' : 'mut';
const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const dfmt = s => { if (!s) return '—'; const p = String(s).split('-'); return p.length < 3 ? String(s) : +p[2] + ' ' + MON[+p[1] - 1] + ' ' + p[0]; };
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const slug = s => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
const CTY = { US: 'United States', NO: 'Norway', CA: 'Canada', TW: 'Taiwan', JP: 'Japan', GB: 'United Kingdom', IN: 'India', FR: 'France', DE: 'Germany', BM: 'Bermuda' };
const chev = '<svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M6 9l6 6 6-6"></path></svg>';
const arrow = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"></path></svg>';

/* ---------- state ---------- */
const S = {
  route: 'universe', unit: 'pct', openCat: {},
  hTab: 'fii', basis: 'pct', hSort: 's', hDir: -1,
  fP: 'A', fG: null,
  // landing page: grouping (cap | sector | watch), market-cap bucket, sector slug ('' = all sectors), index and
  // size filters, search, sort and page of the company table, sort of the sector table
  lc: 'cap', lb: 'large', ls: '', lx: 'all', lz: 'all', uQ: '', uSort: 'm', uDir: -1, uPg: 1, sSort: 'm', sDir: -1,
  watch: store.get('watch', ['ANANDRATHI']), review: store.get('review', {}),
  focus: null, first: true, sym: store.get('sym', 'ANANDRATHI')
};
const ROUTES = ['universe', 'overview', 'holders', 'flows', 'evidence'];
const ALIAS = { fii: ['holders', 'fii'], dii: ['holders', 'dii'], individuals: ['holders', 'ind'], buyers: ['flows'], sellers: ['flows'] };

/* ---------- live prices ---------- */
// prices.js (window.__PX__) is written at deploy time by pipeline/live.py from NSE's daily files.
// Without it (a plain local build) the page uses each snapshot's own prices.
const LP = window.__PX__ || null;
if (LP && LP.univ) U.forEach(u => { const x = LP.univ[u.s]; if (x) { u.p = x[0]; u.q = x[1]; u.m = x[2]; } });
U.sort((a, b) => b.m - a.m);
const sdate = s => { if (!s) return '—'; const p = s.split('-'); return +p[2] + ' ' + MON[+p[1] - 1]; };
const AR_META = { s: 'ANANDRATHI', n: 'Anand Rathi Wealth Ltd', isin: 'INE463V01026', bse: '543415', sector: 'Financial Services', bb: true, oq: true };
let CO, NOW, OQ, OQP, QE, BVPS, DPS, TTM, TTMP, MCAP, SHN, Y1, T, TOT, DEN, FF, PX, HQ, GROUPS, EQ, EQd, REV, PAT, PATO, EPSR, EPSA, EPSADJ, EPS, RET, AR;
function setCompany(sym) {
  D = window.__CO__[sym]; S.sym = sym; store.set('sym', sym);
  if (D.snapshot) return setSnapshot(sym);
  AR = sym === 'ANANDRATHI';
  CO = Object.assign({}, AR ? AR_META : { s: sym, n: sym, bb: false, oq: true }, D.co || {});
  const L = D.live || (LP && LP.co ? LP.co[sym] : null);
  const MULT = L && L.rebased ? L.rebased.m : 1;  // shares per snapshot share after a later split/bonus
  if (!D._init) {
    if (L) {
      const rb = L.rebased;  // a split/bonus went ex after the snapshot: restate earlier prices in today's share terms
      if (rb) D.px_series = D.px_series.filter(r => r[0] <= rb.from).map(r => [r[0]].concat(r.slice(1).map(v => Math.round(v / rb.m * 100) / 100)));
      D.px_series = D.px_series.concat(L.add || []); D.w52 = L.w52;
    }
    // SEBI's percentages exclude shares underlying depository receipts (C1): den = total - dr.
    // 'Others' is the residual of the full total, so the DR shares come out of it into their own line.
    D.trend.forEach(t => { t.dr = t.dr || 0; t.den = t.den || (t.tot - t.dr); t.oth = t.den - t.prom - t.fii - t.dii - t.ind; t.orest = t.oth - t.bc - t.nri; });
    ['fii', 'dii', 'ind'].forEach(g => (D[g] || []).forEach((h, i) => { h.g = g; h.id = slug(h.n); h.rank = i + 1; }));
    D._init = true;
  }
  const ser = D.px_series, lr = ser[ser.length - 1], pr = ser[ser.length - 2];
  NOW = L ? Object.assign({}, L.now, LP.ix.now) : { d: lr[0], c: lr[1], prev: pr[1], n50: D.bench.nifty50[lr[0]], n500: D.bench.nifty500[lr[0]] };
  OQ = L ? L.oq : { d: NOW.d, c: NOW.c };  // close behind the open quarter's "to date" values
  OQP = D.prices[D.prices.length - 1]; QE = D.prices[D.prices.length - 2];  // open quarter · last quarter-end
  if (L) { OQP.d = OQ.d; OQP.c = OQ.raw; OQP.a = OQ.c; OQP.r = OQ.c; OQP.note = OQ.open ? 'quarter still open on ' + OQ.d + '; latest close used' : ''; }
  D.px[D.px.length - 1] = OQ.c * MULT;  // holder share counts are in the snapshot's share terms
  if (D.flows && D.flows.B) ['buy', 'sell', 'all'].forEach(k => D.flows.B[k].forEach(o => { o.v = o.d * OQ.c * MULT / 1e7; }));
  const val = D.val || {};
  BVPS = val.bvps != null ? val.bvps : AR ? 60.1 : null;   // latest book value per share
  DPS = val.dps != null ? val.dps : AR ? 6.5 : null;        // trailing dividend per share, bonus-adjusted
  T = D.trend; TOT = D.tot; DEN = T[T.length - 1].den || TOT; FF = D.ff; PX = D.px; HQ = D.hq;
  GROUPS = { fii: D.fii || [], dii: D.dii || [], ind: D.ind || [] };
  SHN = (CO.shares_now || TOT) * MULT;  // NSE's current share count when known (a merger or QIP after the last filing)
  MCAP = SHN * NOW.c / 1e7;
  Y1 = (+NOW.d.slice(0, 4) - 1) + NOW.d.slice(4);
  const E = D.earn;
  if (E && E.pat && E.pat.length) {
    EQ = E.q; EQd = E.d; REV = E.rev; PAT = E.pat; PATO = E.pat_own || PAT; EPSR = E.eps_rep || E.eps || PAT.map(() => null);
    EPS = PAT.map(p => p * 1e7 / TOT);
    // EPS restated for splits and bonuses: a quarter reported before an action went ex carries EPS on the
    // old share count. Which factor applies is read from the quarter itself: reported EPS x today's shares
    // divided by PAT to owners lands near 1 (already restated) or near the action's ratio (not yet).
    const acts = ((CO.ca || []).filter(a => a[2] === 'split' || a[2] === 'bonus' || (a.length === 2 && a[1] > 1))).sort((a, b) => a[0] < b[0] ? 1 : -1);
    const qe = d => { const m = { Mar: '03-31', Jun: '06-30', Sep: '09-30', Dec: '12-31' }[d.slice(0, 3)]; return '20' + d.slice(4) + '-' + m; };
    EPSADJ = false;
    EPSA = EPSR.map((e, i) => {
      if (e == null || !PATO[i] || !EQd || !EQd[i]) return e;
      const later = acts.filter(a => a[0] > qe(EQd[i]));
      if (!later.length) return e;
      const r = e * SHN / 1e7 / PATO[i];
      let best = 1, f = 1;
      for (const a of later) { f *= a[1]; if (Math.abs(Math.log(r / f)) < Math.abs(Math.log(r / best))) best = f; }
      if (best !== 1 && Math.abs(Math.log(r / best)) < Math.log(1.25)) { EPSADJ = true; return Math.round(e / best * 100) / 100; }
      return e;
    });
    TTM = PATO.slice(-4); TTMP = TTM.length === 4 ? Math.round(TTM.reduce((a, b) => a + b, 0) * 100) / 100 + 1e-9 : null;
  } else { EQ = EQd = REV = PAT = PATO = EPSR = EPS = TTM = null; TTMP = null; }
  const RB = L ? L.bases : RP.filter(p => D.stock_anchor && D.stock_anchor[p[2]]).map(p => { const sa = D.stock_anchor[p[2]]; return { k: p[0], l: p[1], d: sa[0], s: sa[1], sraw: sa[2], ssrc: sa[3], n50: D.bench.nifty50[p[2]], n500: D.bench.nifty500[p[2]], yrs: p[3] }; });
  RET = RB.map(b => {
    const ov = L ? null : ((D.bench.override || {}).nifty500 || {})[b.k];
    const n500 = b.n500 != null ? rcalc(NOW.n500, b.n500, b.yrs) : (ov ? ov[0] : null);
    const pre = (k, name) => b[k + '_pre'] ? name + ' starts ' + dfmt(b[k + '_pre']) + ', after this date' : 'No ' + name + ' close on file for ' + dfmt(b.d);
    return { k: b.k, l: b.l, base: b.d, s: rcalc(NOW.c, b.s, b.yrs), sraw: b.sraw, ssrc: b.ssrc, n50: rcalc(NOW.n50, b.n50, b.yrs), n50b: b.n50, n500, n500b: b.n500, n500src: b.n500 != null ? 'close ' + fin(b.n500, 2) + ' → ' + fin(NOW.n500, 2) : ov ? ov[1] : null, n50na: pre('n50', 'Nifty 50'), n500na: pre('n500', 'Nifty 500'), note: b.note || '' };
  });
  document.title = CO.s + ' · holdermap';
}
function setSnapshot(sym) {
  AR = false;
  CO = Object.assign({ s: sym, n: sym }, D.co || {});
  const L = D.live || (LP && LP.co ? LP.co[sym] : null);
  if (!D._init) { if (L) { D.px_series = D.px_series.concat(L.add || []); D.w52 = L.w52; } D._init = true; }
  const ser = D.px_series, lr = ser[ser.length - 1];
  NOW = L ? Object.assign({}, L.now, LP.ix.now) : { d: lr[0], c: lr[1], prev: CO.ipo_price || lr[1], prevd: 'IPO' };
  const v = D.val || {};
  BVPS = v.bvps; DPS = v.dps; TTMP = v.ttm_pat; TTM = null; SHN = CO.shares_now || D.tot; TOT = D.tot;
  MCAP = SHN * NOW.c / 1e7; T = []; RET = [];
  document.title = CO.s + ' · holdermap';
}
const pct = (a, b) => 100 * a / b;

/* ---------- derived data ---------- */
const CATS = [
  { k: 'prom', l: 'Promoter & group', sub: [] },
  { k: 'fii', l: 'FII / FPI', sub: [['f1', 'FPI Category I'], ['f2', 'FPI Category II'], ['fdi', 'Foreign direct investment (strategic)']] },
  { k: 'dii', l: 'DII', sub: [['mf', 'Mutual funds'], ['ins', 'Insurance companies'], ['aif', 'AIFs']] },
  { k: 'ind', l: 'Individuals', sub: [['iS', 'Holding up to ₹2 lakh'], ['iL', 'Holding above ₹2 lakh']] },
  { k: 'oth', l: 'Others', sub: [['bc', 'Bodies corporate'], ['nri', 'NRIs'], ['orest', 'Trusts, HUFs, clearing & others']] }
];
// Shares underlying ADRs/GDRs sit outside SEBI's percentages; they get their own line (no % value) when a company has them.
const DRCAT = { k: 'dr', l: 'Shares under ADRs / GDRs', sub: [] };
function cats() { return T && T.some(t => t.dr > 0) ? CATS.concat([DRCAT]) : CATS; }
function tv(t, k, u) { if (u === 'pct') return k === 'dr' ? null : k === 'tot' ? 100 : 100 * t[k] / t.den; if (u === 'val') return t[k] * t.px / 1e7; return t[k] * t.bf / 1e6; }
const fmtU = (x, u) => x == null ? '—' : u === 'val' ? fin(x) : x.toFixed(2);
const avg = vs => vs.some(v => v == null) ? null : vs.reduce((a, b) => a + b, 0) / vs.length;
const fmtD = (x, u) => u === 'pct' ? sgn(x, 2, ' pp') : u === 'val' ? sgnI(Math.round(x)) : sgn(x, 2);

function hq(h) { return h.g === 'ind' ? 4 : 5; }
function hMetric(h, i, basis) {
  if (h.s[i] == null || (basis === 'val' && PX[i] == null)) return null;
  const s = h.s[i];
  if (basis === 'pct') return 100 * s / DEN;
  if (basis === 'ff') return h.c === 'Promoter' || !FF[i] ? null : 100 * s / FF[i];
  return s * PX[i] / 1e7;
}
function hStats(h, basis) {
  const n = h.g === 'ind' ? 5 : 6, q = hq(h);
  const vals = []; for (let i = 0; i < n; i++) vals.push(hMetric(h, i, basis));
  const ok = vals.filter(v => v != null);
  const at = i => vals[i] != null ? vals[i] : h.s[i] == null && !(basis === 'val' && PX[i] == null) && !(basis === 'ff' && (h.c === 'Promoter' || !FF[i])) ? 0 : null;
  const a0 = at(0), z = at(n - 1);
  return {
    vals, q, ch: a0 == null || z == null ? null : z - a0, sh: h.s[q] || 0, v: (h.s[q] || 0) * PX[q] / 1e7, pt: 100 * (h.s[q] || 0) / DEN, pff: h.c === 'Promoter' || !FF[q] ? null : 100 * (h.s[q] || 0) / FF[q],
    mean: ok.length ? ok.reduce((a, b) => a + b, 0) / ok.length : null, mx: ok.length ? Math.max.apply(null, ok) : null, mn: ok.length ? Math.min.apply(null, ok) : null
  };
}
const fmtB = (x, basis) => x == null ? '—' : basis === 'val' ? fin(x, 1) : x.toFixed(3);
const fmtBD = (x, basis) => x == null ? '—' : basis === 'val' ? sgn(x, 1) : sgn(x, 3);
const unitB = { pct: '% of total shares', ff: '% of free float', val: '₹ crore' };
function findHolder(name) {
  for (const g of ['fii', 'dii', 'ind']) { const h = GROUPS[g].find(x => x.n === name); if (h) return h; }
  return null;
}

/* ---------- small renderers ---------- */
function seg(id, opts, cur, label) {
  return `<div class="seg" role="group" aria-label="${esc(label)}" data-seg="${id}"><span class="ind" aria-hidden="true"></span>` +
    opts.map(o => `<button type="button" data-set="${id}" data-val="${o[0]}" aria-pressed="${o[0] === cur}">${o[1]}${o[2] != null ? `<span class="ct">${o[2]}</span>` : ''}</button>`).join('') + '</div>';
}
function sh(eb, title, sub, right) {
  return `<div class="sh"><div><div class="eb">${eb}</div><h2>${title}</h2>${sub ? `<p>${sub}</p>` : ''}</div>${right || ''}</div>`;
}
function cu(to, dec, pre, suf) { return `<span data-cu="${to}" data-dec="${dec || 0}" data-pre="${esc(pre || '')}" data-suf="${esc(suf || '')}">${esc(pre || '')}${fin(to, dec || 0)}${esc(suf || '')}</span>`; }

/* ---------- company header ---------- */


function snapHeader() {
  const w = S.watch.includes(CO.s), I = D.ipo || {}, P = D.pattern || {};
  const vsIpo = I.price ? 100 * (NOW.c / I.price - 1) : null;
  const stats = [['Market cap', cu(Math.round(MCAP), 0, '₹', ' cr'), (SHN / 1e7).toFixed(2) + ' cr shares', 'overview'], ['IPO price', '₹' + fin(I.price || 0, 2), (vsIpo == null ? '' : sgn(vsIpo, 1, '%') + ' vs issue price'), 'overview'], ['Shareholders', cu(P.holders_count || 0), 'Before listing, ' + dfmt(P.date), 'holders']];
  const tabs = [['overview', 'Overview'], ['holders', 'Shareholding'], ['flows', 'Buyers &amp; sellers'], ['evidence', 'Sources']];
  return `<section class="co" aria-label="Company summary"><div class="wrap">
  <div class="crumb">${coCrumb(CO.s, CO.sector)}</div>
  <div class="cohead"><div class="coname"><h1>${esc(CO.n)}</h1>
      <div class="chips"><span class="pill" title="An exchange cannot list on itself: NSE's shares trade only on BSE">BSE ONLY · LISTED ${esc(sdate(CO.listed).toUpperCase())}</span>${coCap(U.find(x => x.s === CO.s))}
      <button class="star" type="button" data-act="watch" data-sym="${esc(CO.s)}" aria-pressed="${w}"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"></path></svg><span>${w ? 'Watching' : 'Watch'}</span></button></div></div>
    <div class="px"><div class="pxv"><span class="big">₹${cu(NOW.c, 2)}</span><span class="chg ${cl(NOW.c - NOW.prev)}">${sgn(NOW.c - NOW.prev, 2)} (${sgn(100 * (NOW.c / NOW.prev - 1), 2, '%')})${NOW.prevd === 'IPO' ? ' vs IPO price' : ''}</span><small>BSE close · ${dfmt(NOW.d)}</small></div></div>
  </div>
  <div class="stats">${stats.map(s => `<a class="stat" href="#${s[3]}"><span class="lbl">${s[0]}</span><span class="v">${s[1]}</span><span class="s">${s[2]}</span></a>`).join('')}
    <div class="stat"><span class="lbl">Range since listing</span><span class="v" style="font-size:15px">₹${fin(D.w52.lo, 2)} – ₹${fin(D.w52.hi, 2)}</span><span class="s">BSE, intraday</span></div></div>
  <nav class="tabs" aria-label="Company sections">${tabs.map(t => `<a href="#${t[0]}" data-tab="${t[0]}" ${S.route === t[0] ? 'aria-current="page"' : ''}>${t[1]}</a>`).join('')}<span class="tl" aria-hidden="true"></span></nav>
  </div></section>`;
}
const SNAP_NOTE = 'The full dashboard (FII/DII split, named fund holders, quarter-on-quarter buyers and sellers) starts with NSE\'s first quarterly shareholding filing as a listed company, for the quarter to 30 Sep 2026, due by 21 Oct 2026.';
function snapOverview() {
  const I = D.ipo || {}, P = D.pattern || {}, A = D.earn_annual, Q = D.earn_q;
  const pp = x => (100 * x / D.tot).toFixed(2) + '%';
  const tbl = (E, lab) => `<div class="tscroll"><table class="t"><thead><tr><th class="l">₹ crore</th>${E.q.map(q => `<th>${q}</th>`).join('')}${E.q.length > 1 ? `<th>${lab}</th>` : ''}</tr></thead><tbody>
    ${[['Revenue from ops', E.rev, v => fin(v, 2)], ['PAT to owners', E.pat, v => fin(v, 2)], ['PAT margin', E.pat.map((p, i) => 100 * p / E.rev[i]), v => v.toFixed(1) + '%'], ['EPS, basic (₹)', E.eps, v => v.toFixed(2)]].map(r => `<tr><td class="l">${r[0]}</td>${r[1].map(v => `<td>${r[2](v)}</td>`).join('')}${E.q.length > 1 ? `<td class="${cl(r[1][r[1].length - 1] - r[1][r[1].length - 2])}" style="font-weight:600">${r[0] === 'PAT margin' ? sgn(r[1][r[1].length - 1] - r[1][r[1].length - 2], 1, ' pp') : sgn(100 * (r[1][r[1].length - 1] / r[1][r[1].length - 2] - 1), 1, '%')}</td>` : ''}</tr>`).join('')}</tbody></table></div>`;
  return `<div class="g12">
  <section class="card s5" style="--i:0">${sh('Listing', 'IPO and listing', 'Offer for sale by existing shareholders: no new shares')}
    <div class="tiles">${[['Issue price', '₹' + fin(I.price, 2), 'Band ₹' + fin(I.band[0]) + '–' + fin(I.band[1])], ['Offer size', '₹' + fin(I.size_cr) + ' cr', fin(I.offered) + ' shares'], ['Subscribed', I.subscription + '×', dfmt(I.open) + ' – ' + dfmt(I.close)], ['Listed', dfmt(I.listed), 'BSE · opened ₹' + fin(I.listing_open, 2) + ' (' + sgn(100 * (I.listing_open / I.price - 1), 2, '%') + ')']].map(t => `<div class="tile"><span class="lbl">${t[0]}</span><span class="v">${t[1]}</span><span class="s">${t[2]}</span></div>`).join('')}</div>
    <p class="note grey">Why NSE is outside the Nifty 500 and NSE's price files: an exchange cannot list on itself, so NSE's shares trade only on BSE. Prices here are BSE closes, refreshed every trading day.</p></section>
  <section class="card s7" style="--i:1">${sh('Before listing · ' + dfmt(P.date), 'Shareholding pattern', fin(P.holders_count) + ' shareholders · no promoter group')}
    <div><div class="prow"><span>Public (B)</span><span class="num"><b style="font-weight:600">${pp(P.public)}</b><span class="mut" style="margin-left:10px">${fin(P.public)} sh</span></span></div>
    <div class="prow"><span>Trading members and their associates (C3, non-public)</span><span class="num"><b style="font-weight:600">${pp(P.c3)}</b><span class="mut" style="margin-left:10px">${fin(P.c3)} sh</span></span></div></div>
    <p class="note grey">Pre-offer pattern from the prospectus (SEBI format for an exchange: trading members' holdings sit outside public shareholding). ${SNAP_NOTE}</p></section>
  <section class="card s7" id="earn" style="--i:2">${sh('Earnings', 'Earnings', 'Restated consolidated, ₹ crore (prospectus)')}${tbl(A, 'YoY')}<div style="height:14px"></div>${tbl(Q, 'YoY')}
    <p class="note">FY24 EPS is restated for the 4:1 bonus of Nov 2024. Quarterly results as a listed company start with the quarter to 30 Sep 2026.</p></section>
  <section class="card s5" style="--i:3">${sh('Valuation', 'Valuation', 'Price ₹' + fin(NOW.c, 2) + ' · ' + dfmt(NOW.d))}<div class="tiles">${[['Market cap', '₹' + fin(MCAP) + ' cr', (SHN / 1e7).toFixed(2) + ' cr shares × ₹' + fin(NOW.c, 2)], ['P/E (TTM)', (MCAP / TTMP).toFixed(1) + '×', 'TTM PAT to owners ₹' + fin(TTMP, 1) + ' cr (Q1 FY27 + FY26 − Q1 FY26)'], ['P/B', (NOW.c / BVPS).toFixed(1) + '×', 'Book value ₹' + BVPS.toFixed(2) + ' per share, ' + dfmt(D.val.bs_date)], ['Dividend yield', (100 * DPS / NOW.c).toFixed(2) + '%', D.val.dps_note]].map(t => `<div class="tile" tabindex="0" data-tip="<b>${t[0]}</b><br>${esc(t[2])}"><span class="lbl">${t[0]}</span><span class="v">${t[1]}</span><span class="s">${esc(t[2])}</span></div>`).join('')}</div></section>
  </div>${footer('National Stock Exchange of India Ltd, Red Herring Prospectus dated 10 Sep 2026 (shareholding p.119–121, restated consolidated financials p.79–83, dividends p.66, selling shareholders Annexure A p.623) · BSE daily bhavcopy (scrip 544937) · subscription as reported by the exchanges on 21 Sep 2026.')}`;
}
function snapHolders() {
  const H = D.holders || [], tot = D.tot, f = x => (100 * x / tot).toFixed(2) + '%';
  const sold = H.reduce((a, h) => a + h.sold, 0) + (D.other_sellers || []).reduce((a, h) => a + h.sold, 0);
  return `<div class="kpis" style="--i:0">${[['Holders of 1% or more', H.length, 'Before listing: ' + f(H.reduce((a, h) => a + h.pre, 0)) + ' of shares'], ['Largest holder', 'LIC ' + f(H[0].pre), 'Did not sell in the IPO'], ['Sold in the IPO', fin(sold) + ' sh', f(sold) + ' of shares, by ' + (H.filter(h => h.sold).length + (D.other_sellers || []).length) + ' shareholders'], ['Shareholders', fin(D.pattern.holders_count), 'Before listing']].map(x => `<div class="kpi"><span class="lbl">${x[0]}</span><span class="v">${x[1]}</span><span class="s">${x[2]}</span></div>`).join('')}</div>
  <section class="card" style="--i:1;margin-top:24px">${sh('Shareholding', 'Shareholders with 1% or more', 'Before the IPO (prospectus, ' + dfmt(D.pattern.date) + ') and after the offer for sale')}
  <div class="tscroll"><table class="t"><thead><tr><th class="l">#</th><th class="l">Holder</th><th class="l">Type</th><th class="l">Cty</th><th>Before IPO</th><th>%</th><th>Sold in IPO</th><th>After IPO</th><th>%</th></tr></thead><tbody>
  ${H.map((h, i) => `<tr><td class="l mut">${i + 1}</td><td class="l" style="white-space:normal;min-width:200px;font-weight:500">${esc(h.n)}</td><td class="l mut" style="white-space:normal">${esc(h.c)}</td><td class="l"><span class="chip">${h.cty}</span></td><td>${fin(h.pre)}</td><td>${f(h.pre)}</td><td class="${h.sold ? 'dn' : 'mut'}">${h.sold ? '−' + fin(h.sold) : '—'}</td><td style="font-weight:600">${fin(h.post)}</td><td style="font-weight:600">${f(h.post)}</td></tr>`).join('')}</tbody></table></div>
  <p class="note grey">"After IPO" = before minus the shares each holder offered (prospectus Annexure A); the issue was ${D.ipo.subscription}× subscribed, so all offered shares were sold. Buyers in the IPO are not named until the first quarterly filing. Holder types are descriptive; the prospectus lists names only. ${SNAP_NOTE}</p></section>
  ${footer('Red Herring Prospectus dated 10 Sep 2026: major shareholders p.121, selling shareholders Annexure A p.623.')}`;
}
function snapFlows() {
  const all = D.holders.filter(h => h.sold).map(h => ({ n: h.n, sold: h.sold })).concat(D.other_sellers || []).sort((a, b) => b.sold - a.sold);
  return `<section class="card" style="--i:0">${sh('Sellers', 'Sellers in the IPO', all.length + ' selling shareholders · value at the ₹' + fin(D.ipo.price, 2) + ' issue price')}
  <div class="tscroll"><table class="t"><thead><tr><th class="l">#</th><th class="l">Selling shareholder</th><th>Shares sold</th><th>₹ cr at issue price</th><th>% of shares</th></tr></thead><tbody>
  ${all.map((x, i) => `<tr><td class="l mut">${i + 1}</td><td class="l" style="font-weight:500">${esc(x.n)}</td><td class="dn">−${fin(x.sold)}</td><td>${fin(x.sold * D.ipo.price / 1e7, 1)}</td><td>${(100 * x.sold / D.tot).toFixed(2)}%</td></tr>`).join('')}
  <tr class="tot"><td class="l"></td><td class="l">Total</td><td>−${fin(D.ipo.offered)}</td><td>${fin(D.ipo.size_cr, 1)}</td><td>${(100 * D.ipo.offered / D.tot).toFixed(2)}%</td></tr></tbody></table></div>
  <p class="note grey">Buyers are the IPO allottees (institutions, non-institutional and retail investors). They appear by name only from the first quarterly shareholding filing. ${SNAP_NOTE}</p></section>`;
}
function snapEvidence() {
  return `<section class="card" style="--i:0">${sh('Sources', 'Where every number comes from', 'Primary documents only; nothing estimated')}
  <ul style="line-height:1.9;margin:0;padding-left:18px">
  <li>Red Herring Prospectus dated 10 Sep 2026 — <a href="${esc(D.src)}" target="_blank" rel="noopener" style="color:var(--acc)">PDF</a>: shareholding pattern (p.119–120), holders of 1% or more (p.121), restated consolidated financials (p.79–83), dividends (p.66), selling shareholders (Annexure A, p.623).</li>
  <li>BSE daily bhavcopy, scrip 544937 (ISIN INE721I01024): listing-day and later closes.</li>
  <li>Checks run: every holder's shares reproduce the prospectus percentage; shares offered add up to the 12,64,36,650 in the offer; EPS × 247.5 crore shares = PAT to owners in every period.</li></ul></section>`;
}
function companyHeader() {
  const w = S.watch.includes(CO.s), L5 = T[T.length - 1], L4 = T[T.length - 2];
  const stats = [['Market cap', cu(Math.round(MCAP), 0, '₹', ' cr'), (QE && (QE.r || QE.a) ? sgn(100 * (NOW.c / (QE.r || QE.a) - 1), 1, '%') + ' since ' + sdate(QE.d) : 'No close at the last quarter-end'), 'overview'], ['Free float', (100 - pct(L5.prom, L5.den)).toFixed(2) + '%', L5.q + ' filing', 'holders'], ['Shareholders', cu(L5.nh), L4 ? sgn(100 * (L5.nh / L4.nh - 1), 1, '%') + ' ' + qoqLabel() : 'First filing ' + L5.q, 'overview']];
  const W5 = D.w52, lo = W5.lo, hi = W5.hi;
  const tabs = [['overview', 'Overview'], ['holders', 'Shareholding'], ['flows', 'Buyers &amp; sellers'], ['evidence', 'Evidence &amp; gates']];
  return `<section class="co" aria-label="Company summary"><div class="wrap">
  <div class="crumb">${coCrumb(CO.s, CO.sector)}</div>
  <div class="cohead">
    <div class="coname"><h1>${esc(CO.n)}</h1>
      <div class="chips">${CO.bb ? '' : '<span class="pill" title="Holders from SEBI filings, MF portfolio disclosures and SEC N-PORT; no Bloomberg export">FILINGS</span>'}${(() => { const u = U.find(x => x.s === CO.s); return u ? coCap(u) + memTag(u) : ''; })()}
      <button class="star" type="button" data-act="watch" data-sym="${esc(CO.s)}" aria-pressed="${w}"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"></path></svg><span>${w ? 'Watching' : 'Watch'}</span></button></div>
    </div>
    <div class="px">
      <div class="pxs"><small>Daily close, 1 year, bonus-adjusted</small><div class="chart" data-c="price" style="width:200px;height:44px"></div></div>
      <div class="pxv"><span class="big">₹${cu(NOW.c, 2)}</span><span class="chg ${cl(NOW.c - NOW.prev)}">${sgn(NOW.c - NOW.prev, 2)} (${sgn(100 * (NOW.c / NOW.prev - 1), 2, '%')})</span><small>NSE close · ${dfmt(NOW.d)}</small></div>
    </div>
  </div>
  <div class="stats">${stats.map(s => `<a class="stat" href="#${s[3]}"><span class="lbl">${s[0]}</span><span class="v">${s[1]}</span><span class="s">${s[2]}</span></a>`).join('')}
    <div class="stat" tabindex="0" data-tip="<b>52-week range (intraday)</b><br>Low ₹${fin(lo, 2)} · ${dfmt(W5.lod)}<br>High ₹${fin(hi, 2)} · ${dfmt(W5.hid)}<br>Now ₹${fin(NOW.c, 2)}<br>NSE daily data, bonus-adjusted"><span class="lbl">52-week range</span><span class="v" style="font-size:15px">₹${fin(lo, 2)} – ₹${fin(hi, 2)}</span><span class="s">${(100 * (1 - NOW.c / hi)).toFixed(1)}% below high · ${(100 * (NOW.c / lo - 1)).toFixed(1)}% above low</span></div>
  </div>
  <nav class="tabs" aria-label="Company sections">${tabs.map(t => `<a href="#${t[0]}" data-tab="${t[0]}" ${S.route === t[0] ? 'aria-current="page"' : ''}>${t[1]}</a>`).join('')}<span class="tl" aria-hidden="true"></span></nav>
  </div></section>`;
}

/* ---------- OVERVIEW ---------- */
function qoqLabel() {
  const qi = q => { const m = { Mar: 0, Jun: 1, Sep: 2, Dec: 3 }[q.slice(0, 3)]; return (+q.slice(4)) * 4 + m; };
  const a = T[T.length - 2], b = T[T.length - 1];
  return a && b && qi(b.q) - qi(a.q) === 1 ? 'QoQ' : 'vs ' + (a ? a.q : '—');
}
function ownTable() {
  const u = S.unit;
  let h = `<div class="tscroll"><table class="t"><thead><tr><th class="l" scope="col">Category</th>${T.map(t => `<th scope="col">${t.q}</th>`).join('')}<th scope="col">${qoqLabel()}</th><th scope="col">${T.length}Q Δ</th><th scope="col" data-tip="Average of the ${T.length} filed quarters, in the unit shown">${T.length}Q avg</th></tr></thead><tbody>`;
  cats().forEach(c => {
    const vs = T.map(t => tv(t, c.k, u)), nq = vs.length - 1, na = vs.some(v => v == null), q = na ? null : vs[nq] - vs[nq - 1], s6 = na ? null : vs[nq] - vs[0], open = !!S.openCat[c.k];
    h += `<tr><td class="l"><button type="button" data-act="cat" data-k="${c.k}" aria-expanded="${open}" style="display:inline-flex;align-items:center;gap:6px;background:none;border:0;padding:4px 0;cursor:pointer;font-weight:500;min-height:32px">${c.l}<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true" style="transition:transform .3s var(--ease);transform:rotate(${open ? 180 : 0}deg);color:var(--ink3)"><path d="M6 9l6 6 6-6"></path></svg></button></td>` +
      vs.map((v, i) => `<td data-tip="<b>${c.l} · ${T[i].q}</b><br>${(100 * T[i][c.k] / (c.k === 'dr' ? T[i].tot : T[i].den)).toFixed(2)}%${c.k === 'dr' ? ' of all shares (outside SEBI %)' : ''} · ${fin(T[i][c.k] * T[i].bf)} sh (adj.)<br>₹${fin(T[i][c.k] * T[i].px / 1e7)} cr at ₹${fin(T[i].px, 1)}">${fmtU(v, u)}</td>`).join('') +
      `<td class="${cl(q)}" style="font-weight:600">${fmtD(q, u)}</td><td class="${cl(s6)}">${fmtD(s6, u)}</td><td class="mut">${fmtU(avg(vs), u)}</td></tr>`;
    if (open) {
      h += `<tr class="sub"><td class="l" style="padding-left:28px">Change vs prior quarter</td><td>—</td>${vs.slice(1).map((v, i) => `<td class="${cl(v - vs[i])}">${fmtD(v - vs[i], u)}</td>`).join('')}<td></td><td></td><td></td></tr>`;
      c.sub.forEach(sb => {
        if (!T.some(t => t[sb[0]] > 0)) return;
        const sv = T.map(t => tv(t, sb[0], u));
        h += `<tr class="sub swap"><td class="l" style="padding-left:28px">${sb[1]}</td>${sv.map(v => `<td>${fmtU(v, u)}</td>`).join('')}<td class="${cl(sv[sv.length - 1] - sv[sv.length - 2])}">${fmtD(sv[sv.length - 1] - sv[sv.length - 2], u)}</td><td class="${cl(sv[sv.length - 1] - sv[0])}">${fmtD(sv[sv.length - 1] - sv[0], u)}</td><td>${fmtU(avg(sv), u)}</td></tr>`;
      });
      if (c.k !== 'prom' && c.k !== 'dr') h += `<tr class="sub"><td class="l" style="padding-left:28px" colspan="10"><a href="#${c.k === 'ind' ? 'individuals' : c.k === 'oth' ? 'holders' : c.k}" style="color:var(--acc);font-weight:600;display:inline-flex;gap:6px;align-items:center">${c.k === 'oth' ? 'See named holders' : 'See top holders'} ${arrow}</a></td></tr>`;
    }
  });
  const tl = { pct: 'Total', val: 'Market cap', sh: 'Shares outstanding' }[u], tvs = T.map(t => tv(t, 'tot', u));
  h += `<tr class="tot"><td class="l">${tl}</td>${tvs.map(v => `<td>${fmtU(v, u)}</td>`).join('')}<td class="${u === 'pct' ? '' : cl(tvs[tvs.length - 1] - tvs[tvs.length - 2])}">${u === 'pct' ? '' : fmtD(tvs[tvs.length - 1] - tvs[tvs.length - 2], u)}</td><td class="${u === 'pct' ? '' : cl(tvs[tvs.length - 1] - tvs[0])}">${u === 'pct' ? '' : fmtD(tvs[tvs.length - 1] - tvs[0], u)}</td><td></td></tr>`;
  const nh = T.map(t => t.nh);
  h += `<tr class="sub"><td class="l">Shareholders (count)</td>${nh.map(v => `<td>${fin(v)}</td>`).join('')}<td>${sgn(100 * (nh[nh.length - 1] / nh[nh.length - 2] - 1), 1, '%')}</td><td>${sgn(100 * (nh[nh.length - 1] / nh[0] - 1), 1, '%')}</td><td></td></tr>`;
  return h + '</tbody></table></div>';
}
function ownBody() {
  const cap = { pct: '% of total shares. Tap a category to see its breakdown and quarterly change.', val: '₹ crore at each quarter-end close. Tap a category to see its breakdown.', sh: 'Million shares, adjusted for the Jun-26 1:1 bonus. Tap a category to see its breakdown.' }[S.unit];
  const Lf = T[T.length - 1], drn = Lf.dr_in_public && Lf.filed ? `<p class="note grey">The ${Lf.q} filing counts the ${fin(Lf.dr)} shares underlying ADRs/GDRs (${pct(Lf.dr, Lf.tot).toFixed(2)}% of all shares) inside foreign institutions. They are shown on their own line here so every quarter compares on the same basis. As filed: FII ${(+Lf.filed.fii).toFixed(2)}%, DII ${(+Lf.filed.dii).toFixed(2)}%${Lf.filed.prom != null ? ', promoter ' + (+Lf.filed.prom).toFixed(2) + '%' : ''}.</p>` : T.some(t => t.dr > 0) ? `<p class="note grey">Shares underlying ADRs/GDRs sit outside SEBI's percentages (as in the filings), so they are listed separately and carry no %.</p>` : '';
  return `<span class="cap">${cap}</span>${ownTable()}${drn}`;
}
function viewOverview() {
  const L = T[T.length - 1];
  const qEnd = q => { const m = { Mar: '03-31', Jun: '06-30', Sep: '09-30', Dec: '12-31' }[q.slice(0, 3)]; return '20' + q.slice(4) + '-' + m; };
  const uu = U.find(x => x.s === CO.s), newer = uu && uu.f && uu.f > qEnd(L.q) ? `<p class="note grey">A later filing dated ${dfmt(uu.f)} (after a merger, allotment or sale) shows promoter ${(uu.pr || 0).toFixed(2)}%, FII ${(uu.fi || 0).toFixed(2)}%, DII ${(uu.di || 0).toFixed(2)}%. The universe table uses it; this page stays on quarter-end filings so quarters compare.</p>` : '';
  const tiles = [['Market cap', cu(Math.round(MCAP), 0, '₹', ' cr'), (QE && (QE.r || QE.a) ? sgn(100 * (NOW.c / (QE.r || QE.a) - 1), 1, '%') + ' since ' + sdate(QE.d) : 'No close at the last quarter-end'), 'Shares ' + (SHN / 1e7).toFixed(2) + ' cr' + (SHN !== TOT ? ' (NSE, current)' : '') + ' × ₹' + fin(NOW.c, 2)], ['P/E (TTM)', TTMP > 0 ? cu(+(MCAP / TTMP).toFixed(1), 1, '', '×') : '—', TTMP ? 'On TTM reported PAT ₹' + fin(TTMP, 1) + ' cr' : 'Results not loaded', TTMP ? 'Market cap ₹' + fin(MCAP) + ' cr ÷ PAT' + (PATO !== PAT ? ' attributable to owners' : '') + ' of the last four quarters (₹' + TTM.join(' + ') + ' cr)' : 'No results on file'], ['P/B', BVPS > 0 ? cu(+(NOW.c / BVPS).toFixed(1), 1, '', '×') : BVPS < 0 ? 'n.m.' : '—', BVPS ? 'Book value ₹' + BVPS.toFixed(1) + ' per share' + (BVPS < 0 ? ' (negative equity)' : '') : 'Book value not on file', AR ? 'Mar-26 consolidated equity ≈ ₹999 cr ÷ 166.04 mn shares' : BVPS ? 'Equity attributable to owners ÷ shares, ' + ((D.val || {}).bs_date || 'latest balance sheet') : ''], ['Dividend yield', DPS != null ? cu(+(100 * DPS / NOW.c).toFixed(2), 2, '', '%') : '—', DPS != null ? 'Trailing DPS ₹' + DPS.toFixed(2) : 'Not on file', AR ? '₹6 interim (ex 17 Oct 2025) + ₹7 final (ex 15 May 2026), halved for the Jun-26 bonus' : 'Dividends with an ex-date in the last 12 months (NSE corporate actions)']];
  return `<div class="g12">
  <section class="card s12" id="own" style="--i:0">${sh('Ownership', 'Ownership trend', 'SEBI shareholding pattern, ' + (T.length === 6 ? 'six' : T.length) + ' filed quarters', seg('unit', [['pct', '% of shares'], ['val', 'Value ₹ cr'], ['sh', 'Shares mn']], S.unit, 'Ownership unit'))}<div id="ownBody">${ownBody()}</div>${newer}</section>
  <section class="card s5" style="--i:1">${sh('Valuation', 'Valuation', 'Price ₹' + fin(NOW.c, 2) + ' · ' + dfmt(NOW.d))}<div class="tiles">${tiles.map(t => `<div class="tile" tabindex="0" data-tip="<b>${t[0]}</b><br>${esc(t[3])}"><span class="lbl">${t[0]}</span><span class="v">${t[1]}</span><span class="s">${t[2]}</span></div>`).join('')}</div>${mcapTable()}</section>
  ${earnCard()}
  <section class="card s12" style="--i:3">${sh('Returns', 'Price returns', 'Computed from daily NSE closes · to ' + dfmt(NOW.d))}${retTable()}</section>
  </div>${footer(AR ? 'NSE shareholding patterns (XBRL, SEBI LODR Reg. 31), Mar-25 to Jun-26 · NSE bhavcopy daily closes (stockanalysis.com for 10 Aug–22 Sep 2026, checked against 5 NSE closes) · company results press releases and investor presentations · ' + (LP ? 'Nifty 50 and Nifty 500 closes from NSE\'s daily index files. Prices refresh every trading day from NSE; last close ' + dfmt(NOW.d) + '.' : 'Nifty 50 and Nifty 500 closes as of the snapshot.') + ' Values are shares × NSE close at quarter end (28 Mar 2025 for Mar-25).' : 'NSE shareholding patterns (XBRL, SEBI LODR Reg. 31), ' + T[0].q + ' to ' + T[T.length - 1].q + ' · NSE bhavcopy daily closes, adjusted for bonuses and splits · quarterly results as filed with NSE · Nifty 50 and Nifty 500 closes from NSE\'s daily index files. Prices refresh every trading day; last close ' + dfmt(NOW.d) + '. Values are shares × NSE close at quarter end.')}`;
}
function mcapTable() {
  const R = T.map(t => ({ q: t.q, c: t.px, v: t.px == null ? null : t.tot * t.px / 1e7 })).concat([{ q: 'Now · ' + sdate(NOW.d), c: NOW.c, v: MCAP, now: true }]);
  return `<div class="tscroll"><table class="t"><thead><tr><th class="l" scope="col">Market cap</th><th scope="col">Close ₹</th><th scope="col">₹ crore</th><th scope="col">Change</th></tr></thead><tbody>${R.map((r, i) => { const p = i ? R[i - 1].v : null, d = r.v != null && p ? 100 * (r.v / p - 1) : null; return `<tr${r.now ? ' class="tot"' : ''}><td class="l">${r.now ? r.q : r.q + ' end'}</td><td>${r.c == null ? '—' : fin(r.c, 2)}</td><td style="font-weight:600">${r.v == null ? '—' : fin(Math.round(r.v))}</td><td class="${cl(d)}">${d == null ? '—' : sgn(d, 1, '%')}</td></tr>`; }).join('')}</tbody></table></div><p class="cap" style="margin:0">Shares outstanding at each quarter-end × that day's NSE close${SHN !== TOT ? '; now on NSE\'s current share count' : ''}. Change is against the row above.</p>`;
}
function revLabel() {
  const f = (D.earn && D.earn.format) || '', b = (D.earn && D.earn.basis) || '';
  return f === 'BANKING' || /interest earned/i.test(b) ? 'Interest earned' : f === 'GI' || f === 'LI' || /premium/i.test(b) ? 'Net premium' : 'Revenue from ops';
}
function earnCard() {
  if (!PAT) return `<section class="card s7" id="earn" style="--i:2">${sh('Earnings', 'Earnings', 'Quarterly results')}<p class="cap">Results for ${esc(CO.s)} are not loaded yet.</p></section>`;
  return `<section class="card s7" id="earn" style="--i:2">${sh('Earnings', 'Earnings', '₹ crore · ' + PAT.length + ' reported quarters')}${earnTable()}</section>`;
}
function earnTable() {
  const row = (lab, vs, f, bold, yoy, suf) => `<tr><td class="l" style="font-weight:${bold ? 600 : 500}">${lab}</td>${vs.map((v, i) => `<td style="font-weight:${bold && i === vs.length - 1 ? 600 : 400}">${v == null ? '—' : f(v)}</td>`).join('')}<td class="${cl(yoy)}" style="font-weight:600">${yoy == null ? '<span class="mut" title="Share basis changed">n.m.</span>' : sgn(yoy, 1, suf || '%')}</td></tr>`;
  const h = `<div class="tscroll"><table class="t"><thead><tr><th class="l" scope="col">₹ crore</th>${EQ.map((q, i) => `<th scope="col"><span style="display:block">${q}</span><span style="display:block;font-weight:400;letter-spacing:0;text-transform:none">${EQd[i]}</span></th>`).join('')}<th scope="col">YoY</th></tr></thead><tbody>`;
  const n = PAT.length - 1, y = n - 4, yoy = (a, b) => y >= 0 && a != null && b ? 100 * (a / b - 1) : null;
  return h + `${row(revLabel(), REV, v => fin(v, 2), false, yoy(REV[n], REV[y]))}${row('PAT (reported)', PAT, v => fin(v, 2), true, yoy(PAT[n], PAT[y]))}${PATO !== PAT ? row('PAT to owners', PATO, v => fin(v, 2), false, yoy(PATO[n], PATO[y])) : ''}${row(revLabel() === 'Revenue from ops' ? 'PAT margin' : 'PAT / ' + revLabel().toLowerCase(), PAT.map((p, i) => REV[i] ? 100 * p / REV[i] : null), v => v.toFixed(1) + '%', false, y >= 0 && REV[n] && REV[y] ? 100 * PAT[n] / REV[n] - 100 * PAT[y] / REV[y] : null, ' pp')}${row(AR ? 'EPS as reported (₹)' : 'EPS, basic, as reported (₹)', EPSR, v => v.toFixed(2), !AR && !EPSADJ, AR || EPSADJ ? null : yoy(EPSR[n], EPSR[y]))}${!AR && EPSADJ ? row('EPS, adjusted for splits/bonuses (₹)', EPSA, v => v.toFixed(2), true, yoy(EPSA[n], EPSA[y])) : ''}${AR ? row('EPS on 166.04 mn shares (₹)', EPS, v => v.toFixed(2), true, yoy(EPS[n], EPS[y])) : ''}</tbody></table></div>`;
}
const RP = [['1m', '1 month', '2026-08-21', null], ['3m', '3 months', '2026-06-23', null], ['6m', '6 months', '2026-03-24', null], ['ytd', 'Year to date', '2025-12-31', null], ['1y', '1 year', '2025-09-23', null], ['3y', '3 years, annualised', '2023-09-22', 3], ['sl', 'Since listing, annualised', '2021-12-14', (Date.UTC(2026, 8, 23) - Date.UTC(2021, 11, 14)) / 864e5 / 365.25]];
const LAST = '2026-09-23';
function rcalc(a, b, yrs) { if (a == null || b == null) return null; const r = a / b - 1; return 100 * (yrs ? Math.pow(1 + r, 1 / yrs) - 1 : r); }
// Return bases: from prices.js when live (rolling with the latest close), else the snapshot's fixed anchors.
function retTable() {
  const f = (v, tip) => v == null ? `<span class="mut" data-tip="${esc(tip)}">n/a</span>` : `<span ${tip ? `data-tip="${esc(tip)}"` : ''}>${sgn(v, 2, '%')}</span>`;
  return `<div class="tscroll"><table class="t"><thead><tr><th class="l" scope="col">Period</th><th class="l" scope="col">From</th><th scope="col">${esc(CO.s)}</th><th scope="col">Nifty 50</th><th scope="col">Nifty 500</th><th scope="col">vs Nifty 50</th><th scope="col">vs Nifty 500</th></tr></thead><tbody>${RET.map(r => { const ex = r.n50 == null ? null : r.s - r.n50, ex5 = r.n500 == null ? null : r.s - r.n500; return `<tr><td class="l" style="font-weight:500">${r.l}</td><td class="l mut">${dfmt(r.base)}</td><td class="${cl(r.s)}" style="font-weight:600">${f(r.s, 'Close ₹' + fin(r.sraw, 2) + ' on ' + dfmt(r.base) + (r.sraw !== r.s ? ' (bonus-adjusted base)' : '') + ' → ₹' + fin(NOW.c, 2) + ' · ' + r.ssrc + (r.note ? ' · the price history before this date has a gap that could not be verified, so the long-run return starts here' : ''))}</td><td class="${cl(r.n50)}">${f(r.n50, r.n50 == null ? r.n50na : 'Nifty 50 ' + fin(r.n50b, 2) + ' → ' + fin(NOW.n50, 2))}</td><td class="${cl(r.n500)}">${f(r.n500, r.n500 == null ? r.n500na : 'Nifty 500 · ' + r.n500src)}</td><td class="${cl(ex)}" style="font-weight:600">${ex == null ? '<span class="mut">n/a</span>' : sgn(ex, 1, ' pp')}</td><td class="${cl(ex5)}" style="font-weight:600">${ex5 == null ? '<span class="mut">n/a</span>' : sgn(ex5, 1, ' pp')}</td></tr>`; }).join('')}</tbody></table></div><p class="cap" style="margin:10px 0 0">Price returns, dividends excluded, to the ${dfmt(NOW.d)} close. Stock bases are NSE closes adjusted for bonuses and splits. Hover or tap a figure for its inputs.${RET.some(r => r.n50 == null || r.n500 == null) ? ' n/a means the index had not started yet on that date, or no close is on file; hover a cell for which.' : ''}</p>`;
}

/* ---------- HOLDERS ---------- */
function viewHolders() {
  return `<section class="card" id="hCard" style="--i:0">${holdersHead()}<div id="hBody">${holdersBody()}</div></section>
  ${AR ? footer('holdermap run of 23 Sep 2026 on the Bloomberg Security Ownership export (ANANDRAT IN), reconciled to NSE shareholding filings (7/7 gates). Categories come from SEBI Table II/III, AMFI, IRDAI, SEC registries and GLEIF. Shares are restated for the Jun-26 1:1 bonus. Free float = total shares minus the promoter group in that quarter\'s filing.') : footer('holdermap run of ' + dfmt(D.gen.slice(0, 10)) + (CO.bb ? ' on the Bloomberg Security Ownership export' : ' in filing mode: holders named in SEBI shareholding filings (1% and above), mutual-fund portfolio disclosures (fund-house level) and US fund N-PORT filings') + ', reconciled to NSE shareholding filings (' + D.gates.filter(g => g.ok !== false).length + '/' + D.gates.length + ' gates). Categories come from SEBI Table II/III, AMFI, IRDAI, SEC registries and GLEIF. Free float = total shares minus the promoter group in that quarter\'s filing.')}`;
}
function holdersHead() {
  const title = { fii: 'Top 20 FIIs', dii: 'Top 20 DIIs', ind: 'Top individual holdings' }[S.hTab];
  const sub = { fii: CO.bb ? 'Every foreign holder Bloomberg names with a position today, ranked by shares' : 'Foreign holders named in SEBI filings (1% and above) and US funds from SEC N-PORT filings, ranked by shares', dii: CO.bb ? 'Mutual funds and insurers, grouped at fund-house level' : 'Mutual funds from monthly portfolio disclosures (fund-house level); insurers and others from SEBI filings', ind: D.ind.length + ' individuals and family trusts named in SEBI filings: the promoter group plus public holders above 1%' }[S.hTab];
  return sh('Shareholding', title, sub, seg('hTab', [['fii', 'FIIs', D.fii.length], ['dii', 'DIIs', D.dii.length], ['ind', 'Individuals', D.ind.length]], S.hTab, 'Holder group'));
}
function holdersBody() {
  const L = GROUPS[S.hTab].slice(), b = S.basis, q = S.hTab === 'ind' ? 4 : 5;
  const st = new Map(L.map(h => [h, hStats(h, b)]));
  const key = { n: h => h.n.toLowerCase(), cty: h => h.cty, s: h => st.get(h).sh, v: h => st.get(h).v, pt: h => st.get(h).pt, pff: h => st.get(h).pff == null ? -1 : st.get(h).pff, mean: h => st.get(h).mean || 0, mx: h => st.get(h).mx || 0, mn: h => st.get(h).mn || 0, ch: h => st.get(h).ch == null ? -Infinity : st.get(h).ch }[S.hSort] || (h => st.get(h).sh);
  L.sort((a, c) => { const x = key(a), y = key(c); return (x > y ? 1 : x < y ? -1 : 0) * S.hDir; });
  const asof = S.hTab === 'ind' ? T[T.length - 1].q + ' filing · value at ' + (QE && QE.a ? '₹' + fin(QE.a, 2) + ' (' + dfmt(QE.d) + ')' : 'the quarter-end close') : 'Q3/2026 to date · ' + (CO.oq_src || (CO.bb ? 'Bloomberg, 22 Sep 2026' : 'latest fund disclosures')) + ' · value at ₹' + fin(OQ.c, 2) + ' (' + dfmt(OQ.d) + ')';
  const sortBtn = (k, lab, cls) => `<span class="${cls || ''}"><button type="button" data-sort="h" data-k="${k}" ${S.hSort === k ? `aria-sort="${S.hDir > 0 ? 'ascending' : 'descending'}"` : ''}>${lab}${S.hSort === k ? (S.hDir > 0 ? ' ↑' : ' ↓') : ''}</button></span>`;
  const qlab = S.hTab === 'ind' ? '5Q' : '6Q';
  let h = `<div class="frow"><div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">${seg('basis', [['pct', '% of total'], ['ff', '% of free float'], ['val', 'Value ₹ cr']], b, 'Metric basis')}
    <label class="pm2" style="display:flex;gap:8px;align-items:center;font-size:12px;font-weight:600;color:var(--ink2)">Sort <select class="field" id="hSortSel" data-sortsel="h">${[['s', 'Shares'], ['v', 'Value'], ['pt', '% total'], ['mean', 'Mean'], ['n', 'Name']].map(o => `<option value="${o[0]}" ${S.hSort === o[0] ? 'selected' : ''}>${o[1]}</option>`).join('')}</select></label></div>
    <span class="cap"><b style="color:var(--ink);font-weight:600">As of</b> ${asof}</span></div>
    <div class="legend" style="color:var(--ink3)"><span><span class="flag" style="margin:0 8px 0 0"></span>Category flagged for review</span><span>${qlab} Δ (first to latest quarter), mean, max and min use ${unitB[b]} across ${HQ[0]} to ${HQ[qlab === '6Q' ? 5 : 4]}. Tap a row for quarter-by-quarter detail.</span></div>
    <div role="table" aria-label="${esc(S.hTab)} holders"><div class="lhead gH" role="row"><span class="l">#</span>${sortBtn('n', 'Holder', 'l')}${sortBtn('cty', 'Cty', 'l')}${sortBtn('s', 'Shares mn')}${sortBtn('v', 'Value ₹ cr')}${sortBtn('pt', '% total')}${sortBtn('pff', '% FF')}${sortBtn('ch', qlab + ' Δ')}${sortBtn('mean', 'Mean', 'xm')}${sortBtn('mx', 'Max', 'xm')}${sortBtn('mn', 'Min', 'xm')}<span></span></div>`;
  L.forEach((x, i) => {
    const s = st.get(x);
    const pm = b === 'val' ? `₹${fin(s.v, 1)} cr` : b === 'ff' ? (s.pff == null ? '—' : s.pff.toFixed(3) + '%') : s.pt.toFixed(3) + '%';
    h += `<div class="lrow" data-row="${x.id}" style="--i:${Math.min(i, 20)}"><button type="button" class="rb gH" data-act="row" aria-expanded="false">
      <span class="rk">${x.rank}</span>
      <span class="l" style="min-width:0"><span class="nm">${esc(x.n)}${x.rv ? '<span class="flag" aria-label="Flagged for review"></span>' : ''}</span><span class="sb">${esc(x.sub)}${x.ow ? ' · ' + esc(x.ow) : ''}${x.note ? ' · ' + esc(x.note) : ''}<span class="pm2"> · ${x.cty}</span></span></span>
      <span class="l xp"><span class="chip" title="${CTY[x.cty] || x.cty}">${x.cty}</span></span>
      <span class="xp">${(s.sh / 1e6).toFixed(3)}</span><span class="xp">${fin(s.v, 1)}</span><span class="xp" style="font-weight:600">${s.pt.toFixed(3)}%</span><span class="xp">${s.pff == null ? '—' : s.pff.toFixed(3) + '%'}</span>
      <span class="xp ${cl(s.ch)}">${fmtBD(s.ch, b)}</span>
      <span class="xp xm mut">${fmtB(s.mean, b)}</span><span class="xp xm mut">${fmtB(s.mx, b)}</span><span class="xp xm mut">${fmtB(s.mn, b)}</span>
      <span class="pm2" style="display:flex;flex-direction:column;align-items:flex-end"><b style="font-weight:600">${pm}</b></span>
      ${chev}</button><div class="det"><div></div></div></div>`;
  });
  const tS = L.reduce((a, x) => a + st.get(x).sh, 0), tV = L.reduce((a, x) => a + st.get(x).v, 0);
  h += `<div class="ltot gH"><span class="xp"></span><span class="l">${S.hTab === 'ind' ? 'All ' + L.length + ' combined' : 'Top ' + L.length + ' combined'}</span><span class="xp"></span><span class="xp">${(tS / 1e6).toFixed(3)}</span><span class="xp">${fin(tV, 1)}</span><span class="xp">${(100 * tS / DEN).toFixed(3)}%</span><span class="xp">${S.hTab === 'ind' ? '' : FF[q] ? (100 * tS / FF[q]).toFixed(3) + '%' : '—'}</span><span class="xp"></span><span class="xp xm"></span><span class="xp xm"></span><span class="xp xm"></span><span class="pm pm2">${(100 * tS / DEN).toFixed(2)}% · ₹${fin(tV)} cr</span><span class="xp"></span></div></div>`;
  if (S.hTab === 'fii') {
    const fpd = D.fii_total - (T[T.length - 1].fdi || 0), fps = D.fii.filter(x => x.c !== 'Foreign corporate').reduce((a, x) => a + (x.s[4] || 0), 0);
    if (fpd > 0 && fps > 0) h += fps <= fpd * 1.005
      ? `<p class="note grey">The FPIs in this list hold ${(100 * fps / fpd).toFixed(0)}% of FPI shares at Jun-26. The rest are funds below ${CO.bb ? 'Bloomberg\'s disclosure line' : 'the 1% filing threshold or outside US fund filings'}.</p>`
      : `<p class="note grey">The FPIs in this list add up to ${(100 * fps / fpd).toFixed(0)}% of the FPI shares filed for Jun-26: ${CO.bb ? 'Bloomberg\'s' : 'the disclosed'} counts for some holders run ahead of the filing.</p>`;
  }
  if (S.hTab === 'ind') h += `<p class="note grey">Individuals appear only in quarterly filings. The open quarter updates once the Sep-26 pattern is filed (due by 21 Oct).</p>`;
  return h;
}
function holderDetail(x) {
  const n = x.g === 'ind' ? 5 : 6, qs = HQ.slice(0, n), s = hStats(x, S.basis);
  const rows = qs.map((q, i) => ({ q, sh: x.s[i] || 0, pt: 100 * (x.s[i] || 0) / DEN, pff: x.c === 'Promoter' || !FF[i] ? null : 100 * (x.s[i] || 0) / FF[i], v: PX[i] == null ? null : (x.s[i] || 0) * PX[i] / 1e7 }));
  const inFlow = ['A', 'B'].some(p => D.flows[p] && D.flows[p].all.some(f => f.n === x.n));
  const qt = `<div class="tscroll"><table class="t"><thead><tr><th class="l" scope="col">Quarter</th><th scope="col">Shares</th><th scope="col">Change</th><th scope="col">% of total</th><th scope="col">% FF</th><th scope="col">Value ₹ cr</th></tr></thead><tbody>${rows.map((r, i) => { const d = i ? r.sh - rows[i - 1].sh : null; return `<tr${i === n - 1 ? ' style="font-weight:600"' : ''}><td class="l">${r.q}</td><td>${fin(r.sh)}</td><td class="${cl(d)}">${d == null ? '—' : d ? sgnI(d) : '0'}</td><td>${r.pt.toFixed(3)}%</td><td>${r.pff == null ? '—' : r.pff.toFixed(3) + '%'}</td><td>${r.v == null ? '—' : fin(r.v, 1)}</td></tr>`; }).join('')}</tbody></table></div>`;
  return `<div class="detin">
    <div class="k"><span class="lbl">Shares</span><b>${fin(s.sh)}</b></div>
    <div class="k"><span class="lbl">Value</span><b>₹${fin(s.v, 1)} cr</b></div>
    <div class="k"><span class="lbl">% of total</span><b>${s.pt.toFixed(3)}%</b></div>
    <div class="k"><span class="lbl">% of free float</span><b>${s.pff == null ? '— (promoter)' : s.pff.toFixed(3) + '%'}</b></div>
    <div class="k"><span class="lbl">Mean · Max · Min</span><b style="font-size:13px">${fmtB(s.mean, S.basis)} · ${fmtB(s.mx, S.basis)} · ${fmtB(s.mn, S.basis)}</b><span class="cap">${unitB[S.basis]}</span></div>
    <div class="k"><span class="lbl">Country · type</span><b style="font-size:13px">${CTY[x.cty] || x.cty} · ${esc(x.sub)}</b></div>
    <div class="wide"><span class="lbl">By quarter</span>${qt}</div>
    ${x.rv ? `<div class="wide note">Category is <b>${esc(x.c)}</b> by default. The alternative on file is <b>${esc(x.alt || 'none')}</b>. <a href="#evidence" style="color:var(--acc);font-weight:600">Open the review queue</a></div>` : ''}
    ${inFlow ? `<div class="wide"><button type="button" class="btn" data-go="flows|${D.flows.A && D.flows.A.all.some(f => f.n === x.n) ? 'A' : 'B'}|${esc(x.n)}">See this holder's trades ${arrow}</button></div>` : ''}
  </div>`;
}

/* ---------- FLOWS ---------- */
const GRP = c => c === 'Promoter' ? 'prom' : ['Foreign AMC', 'Foreign Government', 'Foreign Insurance', 'Foreign corporate', 'Bank'].includes(c) ? 'fii' : ['Domestic AMC', 'Domestic Insurance', 'Domestic Pension Fund', 'Government'].includes(c) ? 'dii' : 'ind';
const GL = { prom: 'Promoter group', fii: 'Foreign institutions', dii: 'Domestic institutions', ind: 'Individuals & corporates' };
function viewFlows() {
  return `<div class="frow" style="--i:0">${D.flows.A && D.flows.B && CO.oq !== false ? seg('fP', [['A', (T[T.length - 2] || {}).q + ' → ' + T[T.length - 1].q + ' · filed'], ['B', T[T.length - 1].q + ' → now · latest']], S.fP, 'Comparison period') : ''}<span class="cap">Holder level, from the Bloomberg export reconciled to filings · shares restated for the Jun-26 bonus</span></div>
  <div id="fBody" style="--i:1;margin-top:20px">${flowsBody()}</div>
  ${footer('Buyer or seller = change in shares between two quarter-ends. NEW = no position in the earlier quarter; EXIT = none now.' + (AR ? ' The Anandrathi Housing Finance line is left out: it is the same entity as Twelfth Tier Property, renamed (MCA master data).' : ''))}`;
}
function flowsBody() {
  if (!D.flows.B || CO.oq === false) S.fP = 'A';
  if (!D.flows[S.fP]) S.fP = D.flows.A ? 'A' : 'B';
  if (!D.flows[S.fP]) return `<p class="cap" style="padding:16px 0">No two consecutive filings to compare yet for ${esc(CO.s)}.</p>`;
  const F = D.flows[S.fP], px = S.fP === 'A' ? (QE && QE.a ? '₹' + fin(QE.a, 2) + ' (' + dfmt(QE.d) + ')' : 'the quarter-end close') : '₹' + fin(OQ.c, 2) + ' (' + dfmt(OQ.d) + ')';
  const agg = { prom: 0, fii: 0, dii: 0, ind: 0 }, cnt = { prom: [0, 0], fii: [0, 0], dii: [0, 0], ind: [0, 0] }, nsh = { prom: 0, fii: 0, dii: 0, ind: 0 };
  F.all.forEach(o => { const g = GRP(o.c); agg[g] += o.v; nsh[g] += o.d; cnt[g][o.d > 0 ? 0 : 1]++; });
  const tot = k => Object.keys(GL).reduce((a, g) => a + (k === 'v' ? agg[g] : k === 's' ? nsh[g] : cnt[g][k]), 0);
  const net = `<div class="netrow nh" aria-hidden="true"><span>Holder type</span><span>Buying</span><span>Selling</span><span class="xs">Net shares</span><span>Net ₹ cr</span></div>` + Object.keys(GL).map(g => { const v = agg[g], on = S.fG === g; return `<button type="button" class="netrow" data-act="fgrp" data-g="${g}" aria-pressed="${on}" style="background:${on ? 'var(--surface2)' : 'none'};border-left:3px solid ${on ? 'var(--acc)' : 'transparent'}"><b>${GL[g]}</b><span class="num">${cnt[g][0]}</span><span class="num">${cnt[g][1]}</span><span class="num xs ${cl(nsh[g])}">${nsh[g] ? sgnI(nsh[g]) : '0'}</span><span class="num ${cl(v)}" style="font-weight:600">${sgnC(v)}</span></button>`; }).join('')
    + `<div class="netrow nt"><b>All holders named</b><span class="num">${tot(0)}</span><span class="num">${tot(1)}</span><span class="num xs ${cl(tot('s'))}">${tot('s') ? sgnI(tot('s')) : '0'}</span><span class="num ${cl(tot('v'))}">${sgnC(tot('v'))}</span></div>`;
  const filt = L => S.fG ? L.filter(o => GRP(o.c) === S.fG) : L;
  const buy = filt(S.fG ? F.all.filter(o => o.d > 0).sort((a, b) => b.d - a.d).slice(0, 25) : F.buy), sell = filt(S.fG ? F.all.filter(o => o.d < 0).sort((a, b) => a.d - b.d).slice(0, 25) : F.sell);
  const noteB = AR && S.fP === 'B' ? `<p class="note grey">Five filing-only holders (Amit Rathi, Supriya Saigal, Fahim Sultan Ali, Suhas Gupta Family Trust and Munix India) read 0 in Bloomberg's open quarter. They are held back until the Sep-26 filing confirms an actual exit.</p>` : '';
  const chip = S.fG ? `<button type="button" class="fchip" data-act="fgrp" data-g="${S.fG}" aria-pressed="true">Showing ${GL[S.fG]} <span aria-hidden="true">✕</span></button>` : '';
  return `<div class="g12"><section class="card s12">${sh('Net flow', 'Net flow by holder type', (S.fP === 'A' ? (T[T.length - 2] || {}).q + ' → ' + T[T.length - 1].q : T[T.length - 1].q + ' → ' + (CO.bb ? '22 Sep 2026 (Bloomberg)' : 'latest disclosures')) + ' · value of the change at ' + px + '. Tap a type to filter the lists.', chip)}<div>${net}</div>${noteB}</section>
  <section class="card s6">${sh('Buyers', 'Top 25 buyers', buy.length + ' shown' + (S.fG ? ' · ' + GL[S.fG] : ''))}${flowList(buy, true)}</section>
  <section class="card s6">${sh('Sellers', 'Top 25 sellers', sell.length + ' shown' + (S.fG ? ' · ' + GL[S.fG] : ''))}${flowList(sell, false)}</section></div>`;
}
function flowList(L, buy) {
  if (!L.length) return `<p class="cap" style="padding:16px 0">No ${buy ? 'buyers' : 'sellers'} in this group for the period.</p>`;
  let h = `<div><div class="lhead gF"><span class="l">#</span><span class="l">Holder</span><span>Δ shares</span><span>Δ ₹ cr</span><span>Δ pp</span><span>Now mn</span><span></span></div>`;
  L.forEach((x, i) => {
    const tag = x.t ? `<span class="tag ${buy ? 'b' : 's'}" style="margin-left:8px">${x.t.toUpperCase()}</span>` : '';
    h += `<div class="lrow" data-row="${slug(x.n)}" data-flow="1" style="--i:${Math.min(i, 20)}"><button type="button" class="rb gF" data-act="frow" aria-expanded="false"><span class="rk">${i + 1}</span><span class="l" style="min-width:0"><span class="nm">${esc(x.n)}</span><span class="sb">${x.t ? tag.replace('margin-left:8px', 'margin-right:6px') : ''}${esc(x.sub)} · ${x.cty}</span></span><span class="xp ${buy ? 'up' : 'dn'}" style="font-weight:600">${sgnI(x.d)}</span><span class="xp">${sgnC(x.v)}</span><span class="xp mut">${sgn(100 * x.d / DEN, 3)}</span><span class="xp">${((x.a || 0) / 1e6).toFixed(3)}</span><span class="pm2" style="display:flex;flex-direction:column;align-items:flex-end"><b class="${buy ? 'up' : 'dn'}" style="font-weight:600">${sgnI(x.d)}</b><span style="font-size:11px;color:var(--ink3)">${sgnC(x.v)} cr</span></span>${chev}</button><div class="det"><div></div></div></div>`;
  });
  return h + '</div>';
}
function flowDetail(name) {
  const x = D.flows[S.fP] && D.flows[S.fP].all.find(o => o.n === name); if (!x) return '';
  const h = findHolder(x.n);
  const pc = x.b ? 100 * x.d / x.b : null;
  return `<div class="detin"><div class="k"><span class="lbl">Before</span><b>${fin(x.b)}</b></div><div class="k"><span class="lbl">After</span><b>${fin(x.a)}</b></div><div class="k"><span class="lbl">Change</span><b class="${cl(x.d)}">${pc == null ? 'New position' : sgn(pc, 1, '%')}</b></div><div class="k"><span class="lbl">Δ % of total</span><b>${sgn(100 * x.d / DEN, 3, ' pp')}</b></div><div class="k"><span class="lbl">Category</span><b style="font-size:13px">${esc(x.c)}</b></div>
  ${h ? `<div class="wide"><button type="button" class="btn" data-go="holders|${h.g}|${esc(h.n)}">Open in shareholding ${arrow}</button></div>` : `<div class="wide cap">Not in the current top-20 holder lists.</div>`}</div>`;
}

/* ---------- EVIDENCE ---------- */
const TN = { 'T1-filing': 'T1 · SEBI filing', 'T2-registry': 'T2 · Official registry', 'T3-rule': 'T3 · Legal-form rule', 'override': 'Override, with reason' };
function viewEvidence() {
  Object.keys(D.tiers).forEach(t => { if (!TN[t]) TN[t] = t; });
  const tot = Object.values(D.tiers).reduce((a, b) => a + b, 0);
  const gok = D.gates.filter(g => g.ok !== false).length, g1 = D.gates[0] || { d: '' };
  const k = [['Gates', gok + ' / ' + D.gates.length, (gok === D.gates.length ? 'All passed' : (D.gates.length - gok) + ' failed') + ' · run of ' + D.gen.replace('T', ', ').slice(0, 17), gok === D.gates.length ? 'up' : 'dn'], ['Holders categorised', String(tot), 'By evidence tier, below', ''], ['Counts vs filings', (g1.d.match(/^\d+/) || ['—'])[0], esc(g1.d), ''], ['Flagged for review', String(D.flag.length), 'Default kept, alternative recorded', 'dn']];
  const gates = `<div class="tscroll"><table class="t"><thead><tr><th class="l">#</th><th class="l">Gate</th><th class="l">Result</th><th>Status</th></tr></thead><tbody>${D.gates.map((g, i) => `<tr><td class="l mut" style="width:24px">${i + 1}</td><td class="l" style="font-weight:500;white-space:normal;min-width:160px">${esc(g.n[0].toUpperCase() + g.n.slice(1))}</td><td class="l" style="white-space:normal;color:var(--ink2);min-width:220px">${esc(g.d)}</td><td><span class="pill ${g.ok === false ? 'warn' : 'ok'}">${g.ok === false ? 'FAIL' : 'PASS'}</span></td></tr>`).join('')}</tbody></table></div>`;
  const tiers = `<div>${Object.keys(D.tiers).map(t => `<div class="prow"><span>${TN[t]}</span><span class="num"><b style="font-weight:600">${D.tiers[t]}</b><span class="mut" style="margin-left:10px">${Math.round(100 * D.tiers[t] / tot)}%</span></span></div>`).join('')}</div>`;
  const rec = `<div class="tscroll"><table class="t"><thead><tr><th class="l">Category · Jun-26</th><th>Holder sum</th><th>Filing total</th><th>Ratio</th><th>Band</th></tr></thead><tbody>${D.rec.map(r => `<tr><td class="l" style="white-space:normal;min-width:220px"><b style="font-weight:500">${esc(r.c[0].toUpperCase() + r.c.slice(1))}</b><span style="display:block;font-size:11px;color:var(--ink3);line-height:1.4;margin-top:2px">${esc(r.note)}</span></td><td>${fin(r.b)}</td><td>${fin(r.f)}</td><td style="font-weight:600">${r.r == null ? '—' : r.r.toFixed(3)}</td><td class="mut">${r.band}</td></tr>`).join('')}</tbody></table></div>`;
  const pr = `<div class="tscroll"><table class="t"><thead><tr><th class="l">Quarter</th><th class="l">Trade date</th><th>Close ₹</th><th>Bonus/split</th><th>Adj. ₹</th></tr></thead><tbody>${D.prices.map(p => `<tr ${p.note ? `data-tip="${esc(p.note)}"` : ''}><td class="l" style="font-weight:500">${p.q}</td><td class="l mono" style="font-size:12px">${p.d || '—'}</td><td>${fin(p.c, 2)}</td><td>${p.f == null ? '—' : p.f.toFixed(1) + '×'}</td><td>${p.c == null ? '<span class="mut">not listed</span>' : fin(p.a, 2)}</td></tr>`).join('')}</tbody></table></div>`;
  return `<div class="kpis" style="--i:0">${k.map(x => `<div class="kpi"><span class="lbl">${x[0]}</span><span class="v ${x[3]}">${x[1]}</span><span class="s">${x[2]}</span></div>`).join('')}</div>
  <div class="g12" style="margin-top:24px">
  <section class="card s7" style="--i:1">${sh('Gates', 'Reconciliation gates', 'Every run is checked against the company\'s own filings')}${gates}</section>
  <section class="card s5" style="--i:2">${sh('Provenance', 'How each holder was categorised', tot + ' rows, by evidence tier')}${tiers}</section>
  <section class="card s7" style="--i:3">${sh('Category sums', 'Holder sums vs filing totals', 'Gate 3 detail · quarter Q2/2026')}${rec}</section>
  <section class="card s5" style="--i:4">${sh('Prices', 'Quarter-end prices', 'Value = restated shares × adjusted close')}${pr}</section>
  <section class="card s12" id="rq" style="--i:5">${sh('Review queue', 'Analyst review', 'Rows where the category rests on a registry match or a rule, not a filing. Decisions are saved in this browser.', `<button type="button" class="btn" data-act="rvreset">Reset decisions</button>`)}<div id="rqBody">${reviewBody()}</div></section>
  </div>${footer('Source: holdermap run record ' + esc(CO.s) + '_run.json. Every row\'s evidence sentence and source URL is in the workbook\'s Evidence sheet.')}`;
}
function reviewBody() {
  const done = D.flag.filter(f => S.review[f.n]).length;
  return `<div style="display:flex;justify-content:space-between;align-items:center;gap:12px;font-size:12px;color:var(--ink2)"><span><b style="color:var(--ink)">${done}</b> of ${D.flag.length} reviewed${D.flag.length ? ' · ' + Math.round(100 * done / D.flag.length) + '%' : ''}</span></div>
  <div><div class="rv h"><span>Holder</span><span>Default</span><span>Alternative</span><span>Tier</span><span style="text-align:right">Shares now</span><span style="text-align:right">Decision</span></div>
  ${D.flag.map(f => { const r = S.review[f.n]; return `<div class="rv"><span style="font-weight:500">${esc(f.n)}</span><span class="c2">${esc(f.c)}</span><span class="c3" style="color:var(--acc)">${esc(f.alt || '—')}</span><span class="c4 mono" style="font-size:12px;color:var(--ink3)">${esc(f.tier)}</span><span class="c5 num" style="text-align:right">${fin(f.sh)}</span><span class="acts">${r ? `<span class="done ${r === 'keep' ? 'up' : ''}" style="${r === 'switch' ? 'color:var(--acc)' : ''}">${r === 'keep' ? '✓ Kept ' + esc(f.c) : '→ ' + esc(f.alt || f.c)}</span><button type="button" class="btn" data-act="rv" data-n="${esc(f.n)}" data-v="">Undo</button>` : `<button type="button" class="btn" data-act="rv" data-n="${esc(f.n)}" data-v="keep">Keep</button>${f.alt ? `<button type="button" class="btn pri" data-act="rv" data-n="${esc(f.n)}" data-v="switch">Switch</button>` : ''}`}</span></div>`; }).join('')}</div>`;
}

/* ---------- UNIVERSE (the landing page) ---------- */
// Two ways to group every company, both shown as one Morningstar-style table (Name · Market · Sector · Industry ·
// Market cap):
//  - Market cap: SEBI's categories (large cap = 1st-100th company by full market cap, mid cap = 101st-250th, small
//    cap = 251st onward) as AMFI applies them in its half-yearly list; build.py puts each company's rank in that
//    list in u.ar. SEBI stops at small cap; micro cap splits off the 501st onward, where NSE's Nifty Microcap 250
//    starts. A company AMFI does not list (a listing after its period, a DVR share) is placed by today's market cap
//    against the list's cut-offs (the 100th, 250th and 500th company), and marked.
//  - Sector: the exchanges' classification (NSE and BSE share one: macro-economic sector > sector > industry >
//    basic industry), from pipeline/inputs/industry.json or, until a company is there, NSE's index lists.
const CAP = window.__CAP__ || null;
const BUCKETS = { large: ['Large cap', 1, 100], mid: ['Mid cap', 101, 250], small: ['Small cap', 251, 500], micro: ['Micro cap', 501, null] };
const ord = n => fin(n) + (n % 100 >= 11 && n % 100 <= 13 ? 'th' : ['th', 'st', 'nd', 'rd'][n % 10] || 'th');
U.forEach((u, i) => {
  const r = u.ar || (CAP ? null : i + 1), c = CAP && CAP.cut;  // no list loaded: today's rank
  u.cb = r ? (r <= 100 ? 'large' : r <= 250 ? 'mid' : r <= 500 ? 'small' : 'micro') : u.m >= c[0] ? 'large' : u.m >= c[1] ? 'mid' : u.m >= c[2] ? 'small' : 'micro';
  u.cp = !u.ar && !!CAP;
  u.ss = slug(u.sec || 'not yet classified');
});
const MTOT = U.reduce((a, u) => a + (u.m || 0), 0);
const HAS_IND = U.some(u => u.bi);  // the exchanges' full classification is loaded (pipeline/industry.py)
const MKL = { NB: 'NSE, BSE', N: 'NSE', B: 'BSE' };
const SECTORS = (() => {  // U is in market-cap order, so each sector's first company is its largest
  const m = new Map();
  U.forEach(u => {
    let s = m.get(u.ss);
    if (!s) m.set(u.ss, s = { k: u.ss, n: u.sec || '', c: 0, m: 0, top: u, b: { large: 0, mid: 0, small: 0, micro: 0 } });
    s.c++; s.m += u.m || 0; s.b[u.cb]++;
  });
  return Array.from(m.values());
})();
const BSTAT = {};
Object.keys(BUCKETS).forEach(k => { const L = U.filter(u => u.cb === k); BSTAT[k] = { c: L.length, m: L.reduce((a, u) => a + (u.m || 0), 0), p: L.filter(u => u.cp).length }; });
const MEM = { n500: u => (u.idx || []).includes('n500'), join: u => !!u.n500_from, leave: u => !!u.n500_to, extra: u => !!u.extra };
const MEML = (() => {
  const j = U.find(u => u.n500_from), l = U.find(u => u.n500_to);
  return [['all', 'All companies'], ['n500', 'Nifty 500'], ['join', 'Joining the Nifty 500' + (j ? ' ' + sdate(j.n500_from) : '')], ['leave', 'Leaving the Nifty 500' + (l ? ' ' + sdate(l.n500_to) : '')], ['extra', 'Outside the Nifty 500']];
})();
function memTag(u) {
  return u.n500_from ? `<span class="pill ok" style="margin-left:6px;font-size:10px">JOINS NIFTY 500 ${esc(sdate(u.n500_from).toUpperCase())}</span>`
    : u.n500_to ? `<span class="pill warn" style="margin-left:6px;font-size:10px">LEAVES NIFTY 500 ${esc(sdate(u.n500_to).toUpperCase())}</span>`
    : u.exch === 'BSE' ? `<span class="pill" style="margin-left:6px;font-size:10px">BSE ONLY</span>` : '';
}
const secName = s => s.n || 'Not yet classified';
const lakh = m => m >= 1e5 ? '₹' + fin(m / 1e5, 1) + ' lakh cr' : '₹' + fin(m) + ' cr';  // totals: lakh crore reads easier
const capBasis = () => CAP ? 'AMFI\'s list for ' + CAP.period + (CAP.basis ? ' (' + esc(CAP.basis.charAt(0).toLowerCase() + CAP.basis.slice(1)) + ')' : '') : 'today\'s market cap';
function capTip(u) {  // why a company sits in its category, for tooltips
  return u.ar ? ord(u.ar) + ' of ' + fin(CAP.n) + ' by six-month average market cap in AMFI\'s list for ' + CAP.period
    : u.cp ? 'Not in AMFI\'s list for ' + CAP.period + ': placed by today\'s market cap against its cut-offs' : 'By today\'s market cap';
}
function coCap(u) {  // the category chip on a company page
  return u && u.cb ? `<a class="pill" href="#cap/${u.cb}" title="${esc(capTip(u))}">${BUCKETS[u.cb][0].toUpperCase()}</a>` : '';
}
function coCrumb(sym, fallback) {
  const u = U.find(x => x.s === sym), sec = u && u.sec ? u.sec : fallback;
  return `<a href="#universe">Universe</a>${sec ? `<span>/</span><a href="#sector/${slug(sec)}">${esc(sec)}</a>` : ''}${u && u.ind ? `<span>/</span><span${u.bi ? ` title="${esc(u.mac + ' › ' + u.sec + ' › ' + u.ind + ' › ' + u.bi)}"` : ''}>${esc(u.ind)}</span>` : ''}<span>/</span><span style="color:var(--ink)">${esc(sym)}</span>`;
}
function viewUniverse() {
  const t = { cap: 'Companies by market cap', sector: 'Companies by sector', watch: 'Your watchlist' }[S.lc];
  const asof = LP && LP.asof;
  const body = S.lc === 'watch' ? watchView() : S.lc === 'sector' ? (S.ls ? sectorView() : sectorDir()) : capView();
  return `<div class="lhd" style="--i:0"><div><span class="eb">NSE · BSE${asof ? ' · CLOSE OF ' + esc(dfmt(asof).toUpperCase()) : ''}</span><h1>${t}</h1>
    <p>${fin(U.length)} listed companies, each with its own ownership dashboard: named shareholders, buyers and sellers, earnings, valuation and returns.</p></div>
    <div class="ustat"><div><b>${cu(U.length)}</b><span class="lbl">Companies</span></div><div><b>${cu(U.reduce((a, u) => a + u.h, 0))}</b><span class="lbl">Holder rows</span></div><div><b>${cu(U.filter(u => u.ok).length)}</b><span class="lbl">All gates passed</span></div></div></div>
  <nav class="ltabs" aria-label="Group companies by" style="--i:1"><a href="#cap/${S.lb}" ${S.lc === 'cap' ? 'aria-current="page"' : ''}>Market cap</a><a href="#sector" ${S.lc === 'sector' ? 'aria-current="page"' : ''}>Sector</a><a class="wl" href="#watchlist" ${S.lc === 'watch' ? 'aria-current="page"' : ''}>★ Watchlist<span class="ct">${S.watch.length}</span></a></nav>
  ${body}
  ${footer((CAP ? 'AMFI, average market capitalisation of listed companies, ' + CAP.period + ' (' + fin(CAP.n) + ' companies ranked; ' + esc(CAP.basis || 'SEBI categories') + ') · ' : '') + 'sectors: the exchanges\' industry classification' + (HAS_IND ? ' (NSE and BSE company data)' : ', from NSE\'s index lists') + ' · market cap: latest NSE close × shares outstanding' + (asof ? ', ' + dfmt(asof) : '') + ' · holdermap database, ' + fin(U.length) + ' companies.')}`;
}
function capView() {
  const card = (k, name, sub, c, m, tip) => `<a class="bkc" href="#cap/${k}" ${S.lb === k ? 'aria-current="true"' : ''} title="${esc(tip)}"><span class="bkn">${name}</span><span class="bkr">${sub}</span><b class="num">${fin(c)}</b><span class="bks num">${lakh(m)} · ${(100 * m / MTOT).toFixed(1)}%</span></a>`;
  const cards = Object.keys(BUCKETS).map(k => {
    const B = BUCKETS[k], st = BSTAT[k];
    return card(k, B[0], (B[2] ? ord(B[1]) + ' to ' + ord(B[2]) : ord(B[1]) + ' onward') + (st.p ? ' · +' + st.p + ' not in AMFI\'s list' : ''), st.c, st.m,
      fin(st.c) + ' companies, ₹' + fin(st.m) + ' cr of market cap: ' + (100 * st.m / MTOT).toFixed(1) + '% of the ' + fin(U.length) + ' companies on this page');
  }).join('') + card('all', 'All companies', 'Every size', U.length, MTOT, fin(U.length) + ' companies, ₹' + fin(MTOT) + ' cr of market cap');
  return `<div class="bk" role="group" aria-label="Market-cap category" style="--i:2">${cards}</div><p class="ldef" style="--i:3">${capDef()}</p>${tableSection()}`;
}
function capDef() {
  const b = S.lb, B = BUCKETS[b];
  const np = b === 'all' ? U.filter(u => u.cp).length : B ? BSTAT[b].p : 0;
  const more = (CAP ? 'Cut-offs: ₹' + fin(Math.round(CAP.cut[0])) + ' cr (100th) · ₹' + fin(Math.round(CAP.cut[1])) + ' cr (250th) · ₹' + fin(Math.round(CAP.cut[2])) + ' cr (500th). ' : '')
    + 'Market cap in the table is today\'s.' + (np ? ' ' + fin(np) + ' not in the list yet ' + (np === 1 ? 'is' : 'are') + ' placed by today\'s market cap (marked *).' : '');
  const what = !B ? `All ${fin(U.length)} companies, largest first, grouped by six-month average full market cap in ${capBasis()}.`
    : `<b>${B[0]}:</b> the ${ord(B[1])}${B[2] ? ' to ' + ord(B[2]) : ' company onward'} by six-month average full market cap in ${capBasis()}.`
      + { large: '', mid: '', small: ' SEBI\'s small cap runs from the 251st company onward; this page splits it at the 500th.', micro: ' The part of SEBI\'s small cap below the top 500, where NSE\'s Nifty Microcap 250 starts.' }[b];
  return what + ` <span class="mut">${more}</span>`;
}
function sectorDir() {
  const nc = SECTORS.filter(x => x.n).length, un = SECTORS.find(x => !x.n);
  return `<p class="ldef" style="--i:2">${fin(nc)} sectors in the exchanges' industry classification: NSE and BSE use one structure (macro-economic sector, sector, industry, basic industry) and AMFI uses it for fund portfolios. Pick a sector for its companies.${un ? ' ' + fin(un.c) + ' companies outside NSE\'s index lists are not classified yet.' : ''}</p>
  <section class="lt" style="--i:3"><div class="tscroll" id="sdBody">${sectorTable()}</div></section>`;
}
function sectorTable() {
  const k = { n: x => x.n.toLowerCase(), c: x => x.c, m: x => x.m, top: x => x.top.n.toLowerCase() }[S.sSort] || (x => x.m);
  const L = SECTORS.slice().sort((a, b) => (!a.n - !b.n) || cmpv(k(a), k(b)) * S.sDir);  // not yet classified stays last
  const th = (key, lab, cls) => sortTh('s', key, lab, cls, S.sSort, S.sDir), BK = Object.keys(BUCKETS);
  return `<table class="mt"><thead><tr>${th('n', 'Sector')}${th('c', 'Companies', 'r')}${BK.map(b => plainTh(BUCKETS[b][0].replace(' cap', ''), 'r xm')).join('')}${th('m', 'Market cap (₹ cr)', 'r')}${plainTh('Share', 'r')}${th('top', 'Largest company', 'xm')}</tr></thead><tbody>
  ${L.map(x => `<tr${x.n ? '' : ' class="muted"'}><td><a class="lk" href="#sector/${x.k}">${esc(secName(x))}</a><span class="pm2 sub">Largest: ${esc(x.top.n)}</span></td><td class="r num">${fin(x.c)}</td>${BK.map(b => `<td class="r num xm">${x.b[b] ? fin(x.b[b]) : '<span class="mut">—</span>'}</td>`).join('')}<td class="r num">${fin(x.m)}</td><td class="r num">${(100 * x.m / MTOT).toFixed(1)}%</td><td class="xm"><a class="lk" href="#${encodeURIComponent(x.top.s)}/overview">${esc(x.top.n)}</a></td></tr>`).join('')}
  </tbody><tfoot><tr><td>All companies</td><td class="r num">${fin(U.length)}</td>${BK.map(b => `<td class="r num xm">${fin(BSTAT[b].c)}</td>`).join('')}<td class="r num">${fin(MTOT)}</td><td class="r num">100%</td><td class="xm"></td></tr></tfoot></table>`;
}
function sectorView() {
  const s = SECTORS.find(x => x.k === S.ls);
  if (!s) return `<p class="ldef">No sector called “${esc(S.ls)}”. <a class="lk" href="#sector">See all sectors</a></p>`;
  const chips = [['all', 'All sizes', s.c]].concat(Object.keys(BUCKETS).map(k => [k, BUCKETS[k][0], s.b[k]])).filter(o => o[2] || o[0] === 'all');
  return `<div class="shd" style="--i:2"><a class="back lk" href="#sector">← All sectors</a><h2>${esc(secName(s))}</h2>
    <p class="num">${fin(s.c)} ${s.c === 1 ? 'company' : 'companies'} · ${lakh(s.m)} of market cap · ${(100 * s.m / MTOT).toFixed(1)}% of the total on this page${s.n ? '' : '. These companies are outside NSE\'s index lists; their exchange classification comes with the next data refresh'}</p></div>
  <div class="fchips" role="group" aria-label="Market-cap category" style="--i:3;margin-top:14px">${chips.map(o => `<button type="button" class="fchip" data-set="lz" data-val="${o[0]}" aria-pressed="${S.lz === o[0]}">${o[1]}<span class="ct">${fin(o[2])}</span></button>`).join('')}</div>${tableSection()}`;
}
function watchView() {
  return `<p class="ldef" style="--i:2">${S.watch.length ? 'Companies you are watching, saved in this browser. Open a company and tap Watch to add or remove it.' : 'Your watchlist is empty. Open a company and tap Watch to add it here.'}</p>${S.watch.length ? tableSection() : ''}`;
}
function tableSection() {
  const opts = MEML.map(o => [o[0], o[1], o[0] === 'all' ? null : U.filter(MEM[o[0]]).length]).filter(o => o[2] !== 0);
  return `<section class="lt" id="lt" style="--i:4"><div class="ltool"><label for="uq" class="vh">Search this list</label><input id="uq" class="field" type="search" placeholder="Search by name or symbol" value="${esc(S.uQ)}" autocomplete="off">
    ${S.lc === 'watch' ? '' : `<label class="lsel"><span>Index</span><select class="field" data-sel="lx">${opts.map(o => `<option value="${o[0]}" ${S.lx === o[0] ? 'selected' : ''}>${esc(o[1])}${o[2] != null ? ' (' + fin(o[2]) + ')' : ''}</option>`).join('')}</select></label>`}</div>
    <div id="uBody">${uBody()}</div></section>`;
}
const cmpv = (x, y) => x > y ? 1 : x < y ? -1 : 0;
function uList() {
  const q = S.uQ.trim().toLowerCase();
  let L = S.lc === 'watch' ? U.filter(u => S.watch.includes(u.s))
    : S.lc === 'sector' ? U.filter(u => u.ss === S.ls && (S.lz === 'all' || u.cb === S.lz))
    : U.filter(u => S.lb === 'all' || u.cb === S.lb);
  if (S.lc !== 'watch' && MEM[S.lx]) L = L.filter(MEM[S.lx]);
  if (q) L = L.filter(u => u.n.toLowerCase().includes(q) || u.s.toLowerCase().includes(q));
  const key = { n: u => u.n.toLowerCase(), mk: u => MKL[u.mk] || '', sec: u => (u.sec || '').toLowerCase(), ind: u => (u.ind || '').toLowerCase(), cb: u => u.ar || 1e6 + (1e9 - u.m) / 1e9, m: u => u.m || 0 }[S.uSort] || (u => u.m || 0);
  return L.sort((a, b) => { const x = key(a), y = key(b); return ((x === '') - (y === '')) || cmpv(x, y) * S.uDir || (b.m - a.m); });  // blanks last
}
function sortTh(w, k, lab, cls, cur, dir) {
  const on = cur === k;
  return `<th scope="col" class="${cls || ''}" ${on ? `aria-sort="${dir > 0 ? 'ascending' : 'descending'}"` : ''}><button type="button" class="thb" data-sort="${w}" data-k="${k}"><span class="thl">${lab}</span><span class="si" aria-hidden="true"><i ${on && dir > 0 ? 'class="on"' : ''}>▲</i><i ${on && dir < 0 ? 'class="on"' : ''}>▼</i></span></button></th>`;
}
const plainTh = (lab, cls) => `<th scope="col" class="${cls || ''}"><span class="thb"><span class="thl">${lab}</span><span class="si" aria-hidden="true"></span></span></th>`;
const PG = 50;
function uBody() {
  const L = uList(), pages = Math.max(1, Math.ceil(L.length / PG));
  S.uPg = Math.min(Math.max(1, S.uPg), pages);
  const a = (S.uPg - 1) * PG, shown = L.slice(a, a + PG), th = (k, lab, cls) => sortTh('u', k, lab, cls, S.uSort, S.uDir);
  const inSec = S.lc === 'sector';  // one sector: its column would repeat, so show the market-cap category there
  let h = `<div class="tscroll"><table class="mt co5${HAS_IND ? ' wi' : ''}"><thead><tr>${th('n', 'Name', 'c1')}${th('mk', 'Market', 'xm c2')}${inSec ? th('cb', 'Category', 'xm c3') : th('sec', 'Sector', 'xm c3')}${HAS_IND ? th('ind', 'Industry', 'xm c4') : ''}${th('m', 'Market cap (₹ cr)', 'r c5')}</tr></thead><tbody>`;
  if (!shown.length) h += `<tr><td colspan="5" class="empty">No companies match. Clear the search or pick another filter.</td></tr>`;
  shown.forEach(u => {
    const cls = [inSec ? BUCKETS[u.cb][0] : u.sec, HAS_IND ? u.ind : ''].filter(Boolean).map(esc).join(' · ');
    h += `<tr><td><a class="lk" href="#${encodeURIComponent(u.s)}/overview" title="${esc(u.s)} · ${esc(capTip(u))}">${esc(u.n)}</a>${u.cp ? '<sup class="mut" title="Not in AMFI\'s list yet: placed by today\'s market cap">*</sup>' : ''}${S.watch.includes(u.s) ? '<span class="wst" title="On your watchlist">★</span>' : ''}<span class="pm2 sub">${cls || 'Sector not yet classified'}</span></td>`
      + `<td class="xm">${MKL[u.mk] || 'NSE'}</td><td class="xm">${inSec ? `<span title="${esc(capTip(u))}">${BUCKETS[u.cb][0]}</span>` : u.sec ? esc(u.sec) : '<span class="mut">Not yet classified</span>'}</td>${HAS_IND ? `<td class="xm">${u.ind ? esc(u.ind) : '<span class="mut">—</span>'}</td>` : ''}<td class="r num">${fin(u.m)}</td></tr>`;
  });
  return h + '</tbody></table></div>' + pager(L.length, pages);
}
function pager(n, pages) {
  const p = S.uPg, a = (p - 1) * PG, nums = [];
  for (let i = 1; i <= pages; i++) { if (i === 1 || i === pages || Math.abs(i - p) <= 2) nums.push(i); else if (nums[nums.length - 1] !== 0) nums.push(0); }
  return `<div class="pgr"><span class="cap num">${n ? 'Showing ' + fin(a + 1) + '–' + fin(Math.min(n, a + PG)) + ' of ' + fin(n) : ''}</span>${pages > 1 ? `<nav class="pgn" aria-label="Pages"><button type="button" data-act="pg" data-p="${p - 1}" ${p === 1 ? 'disabled' : ''}>‹ Prev</button>${nums.map(i => i ? `<button type="button" data-act="pg" data-p="${i}" ${i === p ? 'aria-current="page"' : ''}>${i}</button>` : '<span aria-hidden="true">…</span>').join('')}<button type="button" data-act="pg" data-p="${p + 1}" ${p === pages ? 'disabled' : ''}>Next ›</button></nav>` : ''}</div>`;
}
function openSheet(sym) {
  const u = U.find(x => x.s === sym); if (!u) return;
  const ar = DASH.has(u.s), w = S.watch.includes(u.s), pub = Math.max(0, 100 - u.pr - (u.fi || 0) - (u.di || 0));
  $('#sheetRoot').innerHTML = `<div class="scrim" data-act="close"></div><div class="sheet" role="dialog" aria-modal="true" aria-labelledby="shT"><div class="sbody">
   <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start"><div><span class="mono" style="font-size:11px;color:var(--ink3)">${u.s} · ${BUCKETS[u.cb][0].toLowerCase()}</span><h2 id="shT">${esc(u.n)}</h2></div><button type="button" class="x" data-act="close" aria-label="Close"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"></path></svg></button></div>
   <div style="display:flex;align-items:baseline;gap:12px"><span class="num" style="font-size:28px;font-weight:600">₹${fin(u.p, 2)}</span><span class="num ${cl(u.q)}" style="font-weight:600">${sgn(u.q, 1, '%')} QTD</span></div>
   <div class="sgrid"><div><span class="lbl">Promoter</span><b>${(u.pr || 0).toFixed(2)}%</b></div><div><span class="lbl">FII</span><b>${(u.fi || 0).toFixed(2)}%</b></div><div><span class="lbl">DII</span><b>${(u.di || 0).toFixed(2)}%</b></div><div><span class="lbl">Public &amp; others</span><b>${pub.toFixed(2)}%</b></div><div><span class="lbl">Market cap</span><b>₹${fin(u.m)} cr</b></div><div><span class="lbl">Shareholders</span><b>${fin(u.sh)}</b></div><div><span class="lbl">Holders mapped</span><b>${u.h}</b></div><div><span class="lbl">Flagged</span><b>${u.fl}</b></div><div><span class="lbl">Gates</span><b class="${u.ok ? 'up' : 'dn'}">${u.ok ? 'All passed' : 'Needs review'}</b></div><div><span class="lbl">Last filing</span><b class="mono" style="font-size:14px">${u.f || '—'}</b></div></div>
   <div style="display:flex;gap:10px;flex-wrap:wrap"><button type="button" class="star" data-act="watch" data-sym="${u.s}" aria-pressed="${w}" style="min-height:40px"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"></path></svg><span>${w ? 'Watching' : 'Add to watchlist'}</span></button>${ar ? `<a class="btn pri" href="#${encodeURIComponent(u.s)}/overview" data-act="close" style="display:inline-flex;align-items:center;gap:8px;min-height:40px">Open full dashboard ${arrow}</a>` : ''}</div>
   ${ar ? '' : `<p class="note grey">The full dashboard for this company is not built yet. holdermap has its run (${u.h} holders).</p>`}
  </div></div>`;
  document.body.style.overflow = 'hidden';
  setTimeout(() => { const x = $('.sheet .x'); x && x.focus(); }, 50);
}
function closeSheet() { $('#sheetRoot').innerHTML = ''; document.body.style.overflow = ''; }

/* ---------- charts ---------- */
const NS = 'http://www.w3.org/2000/svg';
function svgOpen(w, h, label) { return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(label)}">`; }
const CH = {
  price(el, w) {
    const ser = D.px_series.filter(r => r[0] >= Y1), vals = ser.map(r => r[1]);
    const h = 44, lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    const pts = vals.map((v, i) => [3 + i * (w - 6) / (vals.length - 1), h - 4 - (v - lo) / (hi - lo) * (h - 8)]);
    const p = pts.map(q => q[0].toFixed(1) + ',' + q[1].toFixed(1)).join(' ');
    let s = svgOpen(w, h, 'Share price, daily closes over the last year') + `<polygon points="3,${h} ${p} ${pts[pts.length - 1][0].toFixed(1)},${h}" fill="var(--surface2)"></polygon><polyline class="draw" pathLength="1" points="${p}" fill="none" stroke="var(--ink)" stroke-width="1.6" stroke-linejoin="round"></polyline>`;
    const step = Math.max(1, Math.floor(pts.length / 60));
    pts.forEach((q, i) => { if (i % step && i !== pts.length - 1) return; s += `<rect x="${(q[0] - (w / pts.length) * step / 2).toFixed(1)}" y="0" width="${((w / pts.length) * step).toFixed(1)}" height="${h}" fill="transparent" data-tip="<b>${dfmt(ser[i][0])}</b><br>Close ₹${fin(vals[i], 2)}"></rect>`; });
    s += `<circle cx="${pts[pts.length - 1][0].toFixed(1)}" cy="${pts[pts.length - 1][1].toFixed(1)}" r="3" fill="var(--acc)"></circle>`;
    el.innerHTML = s + '</svg>';
  }
};
function drawCharts(root, still) {
  $$('.chart[data-c]', root).forEach(el => {
    const f = CH[el.dataset.c]; if (!f) return;
    const w = Math.max(160, Math.floor(el.clientWidth));
    f(el, w);
    if (still) $$('.draw', el).forEach(n => { n.style.animation = 'none'; n.style.strokeDashoffset = 0; });
  });
}

/* ---------- segments, tabs, count-up ---------- */
function placeSegs(root) {
  $$('.seg', root).forEach(sg => { const b = $('button[aria-pressed="true"]', sg), ind = $('.ind', sg); if (b && ind) { ind.style.left = b.offsetLeft + 'px'; ind.style.width = b.offsetWidth + 'px'; } });
  const tl = $('.tabs .tl'), cur = $('.tabs a[aria-current="page"]');
  if (tl && cur) { tl.style.left = cur.offsetLeft + 'px'; tl.style.width = cur.offsetWidth + 'px'; }
}
function countUp(root) {
  if (RM) return;
  $$('[data-cu]', root).forEach(el => {
    const to = +el.dataset.cu, dec = +el.dataset.dec, pre = el.dataset.pre, suf = el.dataset.suf, t0 = performance.now(), dur = 800;
    const step = now => { const p = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - p, 3); el.textContent = pre + fin(to * e, dec) + suf; if (p < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  });
}

/* ---------- render ---------- */
function footer(t) { return `<footer class="src" style="--i:6;margin-top:24px">Sources: ${t}</footer>`; }
function openCompany(sym) { location.hash = encodeURIComponent(sym) + '/overview'; }
function withCompany(sym, cb) {
  if (window.__CO__[sym]) return cb();
  const el = document.createElement('script'); el.src = 'co/' + encodeURIComponent(sym) + '.js';
  el.onload = () => { if (window.__CO__[sym]) cb(); else { toast('No dashboard for ' + sym + ' yet'); go('universe'); } };
  el.onerror = () => { toast('No dashboard for ' + sym + ' yet'); S.sym = 'ANANDRATHI'; go('universe'); };
  document.head.appendChild(el);
}
function parseHash() {
  let h = decodeURIComponent((location.hash || '').replace('#', ''));
  // The landing page: #universe, #cap/<bucket>, #sector, #sector/<slug>, #watchlist. A bare address (a new tab,
  // the access link) always opens it; company pages need their own link (#SYM/overview).
  const lm = /^(universe|cap|sector|watchlist)(?:\/(.*))?$/.exec(h);
  if (!h || lm) {
    const k = lm ? lm[1] : 'universe', arg = (lm && lm[2]) || '';
    const lc = k === 'watchlist' ? 'watch' : k === 'sector' ? 'sector' : 'cap';
    const lb = lc !== 'cap' ? S.lb : k === 'cap' && (BUCKETS[arg] || arg === 'all') ? arg : 'large', ls = lc === 'sector' ? arg : S.ls;
    if (lc !== S.lc || lb !== S.lb || ls !== S.ls) { S.uPg = 1; if (ls !== S.ls) S.lz = 'all'; }  // back from a company keeps the page
    S.route = 'universe'; S.lc = lc; S.lb = lb; S.ls = ls;
    return;
  }
  const sl = h.indexOf('/');
  if (sl > 0) { S.sym = h.slice(0, sl); h = h.slice(sl + 1) || 'overview'; }
  else if (!ROUTES.includes(h) && !ALIAS[h] && U.some(u => u.s === h)) { S.sym = h; h = 'overview'; }
  if (ALIAS[h]) { S.route = ALIAS[h][0]; if (ALIAS[h][1]) S.hTab = ALIAS[h][1]; return; }
  S.route = ROUTES.includes(h) ? h : 'overview';
}
function render() {
  const company = S.route !== 'universe';
  if (company && (!D || D !== window.__CO__[S.sym])) return withCompany(S.sym, () => { setCompany(S.sym); render(); });
  const prevLast = document.documentElement.dataset.route;
  $('#co').innerHTML = company ? (D && D.snapshot ? snapHeader() : companyHeader()) : '';
  const main = $('#main');
  main.innerHTML = (company && D && D.snapshot ? { overview: snapOverview, holders: snapHolders, flows: snapFlows, evidence: snapEvidence } : { universe: viewUniverse, overview: viewOverview, holders: viewHolders, flows: viewFlows, evidence: viewEvidence })[S.route]();
  main.classList.remove('view'); void main.offsetWidth; main.classList.add('view');
  document.documentElement.dataset.route = S.route;
  $$('.tnav a').forEach(a => { const on = (a.dataset.nav === 'universe' && S.route === 'universe' && S.lc !== 'watch') || (a.dataset.nav === 'watchlist' && S.route === 'universe' && S.lc === 'watch') || (a.dataset.nav === 'company' && company); on ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current'); });
  $$('.bnav a').forEach(a => a.dataset.b === S.route ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current'));
  const nc = $('#navCo'); if (nc) { const u = U.find(x => x.s === S.sym); nc.textContent = (company && CO ? CO.n : u ? u.n : S.sym).replace(/ (Limited|Ltd\.?)$/i, ''); nc.href = '#' + encodeURIComponent(S.sym) + '/overview'; }
  const nd = $('#navDt'); if (nd) nd.textContent = 'NSE close · ' + dfmt(company && NOW ? NOW.d : LP ? LP.asof : U.length ? '2026-09-23' : '');
  document.title = company && CO ? CO.s + ' · holdermap' : 'holdermap';
  requestAnimationFrame(() => {
    drawCharts(document); placeSegs(document); if (S.first || prevLast !== S.route) countUp(document); S.first = false; focusPending();
    const bc = $('.bkc[aria-current="true"]'), row = bc && bc.parentElement;  // phones: the category cards scroll sideways
    if (row && row.scrollWidth > row.clientWidth) row.scrollLeft = Math.max(0, bc.offsetLeft - row.offsetLeft - 16);
  });
}
function patch(id, fn) {
  const el = $('#' + id); if (!el) return;
  el.innerHTML = fn();
  el.classList.remove('swap'); void el.offsetWidth; el.classList.add('swap');
  requestAnimationFrame(() => { drawCharts(el); placeSegs(el.closest('section') || el); placeSegs(document); });
}
function go(route) { if (location.hash === '#' + route) { parseHash(); render(); } else location.hash = route; window.scrollTo({ top: 0, behavior: 'auto' }); }
function focusPending() {
  if (!S.focus) return;
  const id = slug(S.focus); S.focus = null;
  const row = $(`.lrow[data-row="${id}"]`); if (!row) return;
  toggleRow(row, true);
  setTimeout(() => { row.scrollIntoView({ behavior: RM ? 'auto' : 'smooth', block: 'center' }); row.animate && !RM && row.animate([{ boxShadow: 'inset 3px 0 0 var(--acc)', background: 'var(--accSoft)' }, { boxShadow: 'inset 3px 0 0 transparent', background: 'transparent' }], { duration: 1800, easing: 'ease-out' }); }, 120);
}
function toggleRow(row, force) {
  const btn = $('.rb', row), det = $('.det>div', row), open = force != null ? force : !row.classList.contains('open');
  if (open && !det.innerHTML) {
    const id = row.dataset.row;
    if (row.dataset.flow) { const f = D.flows[S.fP] && D.flows[S.fP].all.find(o => slug(o.n) === id); det.innerHTML = f ? flowDetail(f.n) : ''; }
    else { const h = GROUPS[S.hTab].find(x => x.id === id); det.innerHTML = h ? holderDetail(h) : ''; }
    void row.offsetWidth;
  }
  row.classList.toggle('open', open); btn.setAttribute('aria-expanded', open);
}
function toast(msg) { const t = $('#toast'); t.textContent = msg; t.classList.add('on'); clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove('on'), 2200); }

/* ---------- events ---------- */
document.addEventListener('click', e => {
  const t = e.target.closest('[data-set],[data-act],[data-go],[data-sort]');
  if (!t) return;
  if (t.dataset.set) {
    const k = t.dataset.set, v = t.dataset.val;
    if (S[k] === v && k !== 'hTab') return;
    S[k] = v;
    if (k === 'unit') patch('ownBody', ownBody);
    else if (k === 'hTab') { S.hSort = 's'; S.hDir = -1; const c = $('#hCard'); if (c) { c.firstElementChild.outerHTML = holdersHead(); patch('hBody', holdersBody); } }
    else if (k === 'basis') patch('hBody', holdersBody);
    else if (k === 'fP') { S.fG = null; patch('fBody', flowsBody); }
    else if (k === 'lz') { S.uPg = 1; patch('uBody', uBody); }
    $$(`[data-set="${k}"]`).forEach(b => b.setAttribute('aria-pressed', b.dataset.val === S[k]));
    requestAnimationFrame(() => placeSegs(document));
    return;
  }
  if (t.dataset.sort) {
    const w = t.dataset.sort, k = t.dataset.k;
    if (w === 'h') { if (S.hSort === k) S.hDir *= -1; else { S.hSort = k; S.hDir = k === 'n' || k === 'cty' ? 1 : -1; } patch('hBody', holdersBody); }
    else if (w === 's') { if (S.sSort === k) S.sDir *= -1; else { S.sSort = k; S.sDir = k === 'n' || k === 'top' ? 1 : -1; } patch('sdBody', sectorTable); }
    else { if (S.uSort === k) S.uDir *= -1; else { S.uSort = k; S.uDir = k === 'm' ? -1 : 1; } S.uPg = 1; patch('uBody', uBody); }  // category sorts by AMFI rank
    return;
  }
  if (t.dataset.go) {
    e.preventDefault();
    const p = t.dataset.go.split('|');
    if (p[0] === 'flows') { S.fP = p[1]; S.fG = null; S.focus = p[2]; go('flows'); }
    else if (p[0] === 'holders') { S.hTab = p[1]; S.focus = p[2] || null; S.hSort = 's'; S.hDir = -1; S.basis = 'pct'; go('holders'); }
    return;
  }
  const a = t.dataset.act;
  if (a === 'cat') { S.openCat[t.dataset.k] = !S.openCat[t.dataset.k]; patch('ownBody', ownBody); }
  else if (a === 'row' || a === 'frow') toggleRow(t.closest('.lrow'));
  else if (a === 'fgrp') { S.fG = S.fG === t.dataset.g ? null : t.dataset.g; patch('fBody', flowsBody); }
  else if (a === 'sheet') { if (DASH.has(t.dataset.sym) && t.classList.contains('rb')) openCompany(t.dataset.sym); else openSheet(t.dataset.sym); }
  else if (a === 'close') { closeSheet(); }
  else if (a === 'pg') { S.uPg = +t.dataset.p; patch('uBody', uBody); const lt = $('#lt'); if (lt) lt.scrollIntoView({ behavior: RM ? 'auto' : 'smooth', block: 'start' }); }
  else if (a === 'watch') {
    const s = t.dataset.sym, i = S.watch.indexOf(s);
    if (i >= 0) S.watch.splice(i, 1); else S.watch.push(s);
    store.set('watch', S.watch);
    const on = S.watch.includes(s);
    $$(`[data-act="watch"][data-sym="${s}"]`).forEach(b => { b.setAttribute('aria-pressed', on); $('span', b).textContent = on ? 'Watching' : (b.closest('.sheet') ? 'Add to watchlist' : 'Watch'); });
    toast(on ? 'Added to watchlist' : 'Removed from watchlist');
    if (S.route === 'universe' && !t.closest('.sheet')) render();
  }
  else if (a === 'rv') { const n = t.dataset.n, v = t.dataset.v; if (v) S.review[n] = v; else delete S.review[n]; store.set('review', S.review); patch('rqBody', reviewBody); toast(v === 'keep' ? 'Category kept' : v === 'switch' ? 'Switched to the alternative' : 'Decision undone'); }
  else if (a === 'rvreset') { S.review = {}; store.set('review', S.review); patch('rqBody', reviewBody); toast('Decisions cleared'); }
});
document.addEventListener('change', e => {
  if (e.target.dataset.sortsel === 'h') { S.hSort = e.target.value; S.hDir = e.target.value === 'n' ? 1 : -1; patch('hBody', holdersBody); }
  if (e.target.dataset.sel === 'lx') { S.lx = e.target.value; S.uPg = 1; patch('uBody', uBody); }
});
let uqT;
document.addEventListener('input', e => {
  if (e.target.id === 'uq') { clearTimeout(uqT); S.uQ = e.target.value; S.uPg = 1; uqT = setTimeout(() => patch('uBody', uBody), 120); }
  if (e.target.id === 'q') gsearch(e.target.value);
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') { if ($('.sheet')) closeSheet(); gsClose(); $('#top').classList.remove('searching'); }
  if (e.key === '/' && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) { e.preventDefault(); if (window.innerWidth <= 760) $('#top').classList.add('searching'); $('#q').focus(); }
});
window.addEventListener('hashchange', () => { closeSheet(); parseHash(); render(); window.scrollTo(0, 0); });
let rT; window.addEventListener('resize', () => { clearTimeout(rT); rT = setTimeout(() => { drawCharts(document, true); placeSegs(document); }, 120); });

/* global search */
let gsSel = 0, gsItems = [];
function gsearch(v) {
  const r = $('#gsres'), q = v.trim().toLowerCase();
  if (!q) { gsClose(); return; }
  gsItems = U.filter(u => u.n.toLowerCase().includes(q) || u.s.toLowerCase().includes(q)).slice(0, 8); gsSel = 0;
  r.hidden = false; $('#q').setAttribute('aria-expanded', 'true');
  r.innerHTML = gsItems.length ? gsItems.map((u, i) => `<button type="button" role="option" data-gs="${u.s}" class="${i === 0 ? 'act' : ''}"><span><b style="font-weight:600">${esc(u.n)}</b><span class="mono" style="display:block;font-size:11px;color:var(--ink3)">${u.s}</span></span><span class="num" style="font-size:12px;color:var(--ink2)">₹${fin(u.m)} cr</span></button>`).join('') : `<div class="empty">No company matches “${esc(v)}”.</div>`;
}
function gsClose() { const r = $('#gsres'); r.hidden = true; r.innerHTML = ''; $('#q').setAttribute('aria-expanded', 'false'); }
function gsPick(sym) { gsClose(); $('#q').value = ''; $('#top').classList.remove('searching'); if (DASH.has(sym)) openCompany(sym); else openSheet(sym); }
$('#gsres').addEventListener('click', e => { const b = e.target.closest('[data-gs]'); if (b) gsPick(b.dataset.gs); });
$('#q').addEventListener('keydown', e => {
  if (!gsItems.length) return;
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); gsSel = (gsSel + (e.key === 'ArrowDown' ? 1 : -1) + gsItems.length) % gsItems.length; $$('#gsres [data-gs]').forEach((b, i) => b.classList.toggle('act', i === gsSel)); }
  if (e.key === 'Enter') { e.preventDefault(); gsPick(gsItems[gsSel].s); }
});
$('#q').addEventListener('blur', () => setTimeout(() => { gsClose(); if (!$('#q').value) $('#top').classList.remove('searching'); }, 180));
$('#srchBtn').addEventListener('click', () => { $('#top').classList.add('searching'); $('#q').focus(); });

/* theme */
const THEMES = ['system', 'light', 'dark'];
let theme = store.get('theme', 'system');
function applyTheme() { if (theme === 'system') document.documentElement.removeAttribute('data-theme'); else document.documentElement.setAttribute('data-theme', theme); $('#themeBtn').setAttribute('aria-label', 'Theme: ' + theme); $('#themeBtn').title = 'Theme: ' + theme; }
$('#themeBtn').addEventListener('click', () => { theme = THEMES[(THEMES.indexOf(theme) + 1) % 3]; store.set('theme', theme); applyTheme(); toast('Theme: ' + theme); });
applyTheme();

/* tooltip */
const tip = $('#tip'); let tipT;
function showTip(el, x, y) { tip.innerHTML = el.getAttribute('data-tip'); tip.classList.add('on'); const r = tip.getBoundingClientRect(); let L = x + 14, Tp = y + 14; if (L + r.width > window.innerWidth - 8) L = x - r.width - 14; if (Tp + r.height > window.innerHeight - 8) Tp = y - r.height - 14; tip.style.left = Math.max(8, L) + 'px'; tip.style.top = Math.max(8, Tp) + 'px'; }
document.addEventListener('pointermove', e => { if (e.pointerType !== 'mouse') return; const el = e.target.closest && e.target.closest('[data-tip]'); if (el) showTip(el, e.clientX, e.clientY); else tip.classList.remove('on'); });
document.addEventListener('pointerdown', e => { if (e.pointerType === 'mouse') return; const el = e.target.closest && e.target.closest('[data-tip]'); if (el) { showTip(el, e.clientX, e.clientY); clearTimeout(tipT); tipT = setTimeout(() => tip.classList.remove('on'), 2600); } else tip.classList.remove('on'); });
document.addEventListener('focusin', e => { const el = e.target.closest && e.target.closest('[data-tip]'); if (el && el.getBoundingClientRect) { const r = el.getBoundingClientRect(); showTip(el, r.left + r.width / 2, r.bottom); } });
document.addEventListener('focusout', () => tip.classList.remove('on'));
window.addEventListener('scroll', () => tip.classList.remove('on'), { passive: true });

parseHash(); render();
})();
