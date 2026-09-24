(function(){
"use strict";
const D = window.__HM__;
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
const cl = x => x > 0 ? 'up' : x < 0 ? 'dn' : 'mut';
const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const dfmt = s => { const p = s.split('-'); return +p[2] + ' ' + MON[+p[1] - 1] + ' ' + p[0]; };
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const slug = s => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
const CTY = { US: 'United States', NO: 'Norway', CA: 'Canada', TW: 'Taiwan', JP: 'Japan', GB: 'United Kingdom', IN: 'India', FR: 'France', DE: 'Germany', BM: 'Bermuda' };
const chev = '<svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M6 9l6 6 6-6"></path></svg>';
const arrow = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"></path></svg>';

/* ---------- state ---------- */
const S = {
  route: 'overview', unit: 'pct', openCat: {}, eMetric: 'pat', rH: '1y',
  hTab: 'fii', basis: 'pct', hSort: 's', hDir: -1,
  fP: 'A', fG: null,
  uB: 'all', uQ: '', uSort: 'm', uDir: -1, uN: 20,
  watch: store.get('watch', ['ANANDRATHI']), review: store.get('review', {}),
  focus: null, first: true
};
const ROUTES = ['universe', 'watchlist', 'overview', 'holders', 'flows', 'evidence'];
const ALIAS = { fii: ['holders', 'fii'], dii: ['holders', 'dii'], individuals: ['holders', 'ind'], buyers: ['flows'], sellers: ['flows'] };

/* ---------- live prices ---------- */
// prices.js (window.__PX__) is written at deploy time by pipeline/live.py from NSE's daily files.
// Without it (a plain local build) the page uses the snapshot's own prices in data.js.
const LP = window.__PX__ || null;
if (LP) {
  D.px_series = LP.series; D.w52 = LP.w52;
  D.univ.forEach(u => { const x = LP.univ[u.s]; if (x) { u.p = x[0]; u.q = x[1]; u.m = x[2]; } });
  D.univ.sort((a, b) => b.m - a.m);
}
const LASTR = D.px_series[D.px_series.length - 1], PREVR = D.px_series[D.px_series.length - 2];
const NOW = LP ? LP.now : { d: LASTR[0], c: LASTR[1], prev: PREVR[1], n50: D.bench.nifty50[LASTR[0]], n500: D.bench.nifty500[LASTR[0]] };
const OQ = LP ? LP.oq : { d: NOW.d, c: NOW.c };  // close behind the open quarter's "to date" values
const OQP = D.prices[D.prices.length - 1], QE = D.prices[D.prices.length - 2];  // open quarter · last quarter-end
if (LP) { OQP.d = OQ.d; OQP.c = OQ.raw; OQP.a = OQ.c; OQP.note = OQ.open ? 'quarter still open on ' + OQ.d + '; latest close used' : ''; }
D.px[D.px.length - 1] = OQ.c;
['buy', 'sell', 'all'].forEach(k => D.flows.B[k].forEach(o => { o.v = o.d * OQ.c / 1e7; }));
const BVPS = 60.1, DPS = 6.5;  // Mar-26 book value per share; trailing DPS, bonus-adjusted
const TTM = D.earn.pat.slice(-4), TTMP = Math.round(TTM.reduce((a, b) => a + b, 0) * 100) / 100 + 1e-9;
const MCAP = D.tot * NOW.c / 1e7;
const Y1 = (+NOW.d.slice(0, 4) - 1) + NOW.d.slice(4);
const sdate = s => { const p = s.split('-'); return +p[2] + ' ' + MON[+p[1] - 1]; };

/* ---------- derived data ---------- */
const T = D.trend, TOT = D.tot, FF = D.ff, PX = D.px, HQ = D.hq;
T.forEach(t => { t.orest = t.oth - t.bc - t.nri; });
const CATS = [
  { k: 'prom', l: 'Promoter & group', sub: [] },
  { k: 'fii', l: 'FII / FPI', sub: [['f1', 'FPI Category I'], ['f2', 'FPI Category II']] },
  { k: 'dii', l: 'DII', sub: [['mf', 'Mutual funds'], ['ins', 'Insurance companies'], ['aif', 'AIFs']] },
  { k: 'ind', l: 'Individuals', sub: [['iS', 'Holding up to ₹2 lakh'], ['iL', 'Holding above ₹2 lakh']] },
  { k: 'oth', l: 'Others', sub: [['bc', 'Bodies corporate'], ['nri', 'NRIs'], ['orest', 'Trusts, HUFs, clearing & others']] }
];
const CC = { prom: 'var(--prom)', fii: 'var(--fii)', dii: 'var(--dii)', ind: 'var(--ind)', oth: 'var(--oth)' };
function tv(t, k, u) { if (u === 'pct') return 100 * t[k] / t.tot; if (u === 'val') return t[k] * t.px / 1e7; return t[k] * t.bf / 1e6; }
const fmtU = (x, u) => u === 'val' ? fin(x) : x.toFixed(2);
const fmtD = (x, u) => u === 'pct' ? sgn(x, 2, ' pp') : u === 'val' ? sgnI(Math.round(x)) : sgn(x, 2);

const GROUPS = { fii: D.fii, dii: D.dii, ind: D.ind };
Object.keys(GROUPS).forEach(g => GROUPS[g].forEach((h, i) => { h.g = g; h.id = slug(h.n); h.rank = i + 1; }));
function hq(h) { return h.g === 'ind' ? 4 : 5; }
function hMetric(h, i, basis) {
  const s = h.s[i] || 0;
  if (basis === 'pct') return 100 * s / TOT;
  if (basis === 'ff') return h.c === 'Promoter' ? null : 100 * s / FF[i];
  return s * PX[i] / 1e7;
}
function hStats(h, basis) {
  const n = h.g === 'ind' ? 5 : 6, q = hq(h);
  const vals = []; for (let i = 0; i < n; i++) vals.push(hMetric(h, i, basis));
  const ok = vals.filter(v => v != null);
  return {
    vals, q, sh: h.s[q] || 0, v: (h.s[q] || 0) * PX[q] / 1e7, pt: 100 * (h.s[q] || 0) / TOT, pff: h.c === 'Promoter' ? null : 100 * (h.s[q] || 0) / FF[q],
    mean: ok.length ? ok.reduce((a, b) => a + b, 0) / ok.length : null, mx: ok.length ? Math.max.apply(null, ok) : null, mn: ok.length ? Math.min.apply(null, ok) : null,
    d: (h.s[q] || 0) - (h.s[q - 1] || 0)
  };
}
const fmtB = (x, basis) => x == null ? '—' : basis === 'val' ? fin(x, 1) : x.toFixed(3);
const unitB = { pct: '% of total shares', ff: '% of free float', val: '₹ crore' };
function findHolder(name) {
  for (const g of ['fii', 'dii', 'ind']) { const h = GROUPS[g].find(x => x.n === name); if (h) return h; }
  return null;
}

/* ---------- small renderers ---------- */
function spark(vals, w, h, color, opts) {
  opts = opts || {};
  const v = vals.map(x => x == null ? 0 : x);
  const lo = Math.min.apply(null, v), hi = Math.max.apply(null, v), r = (hi - lo) || 1;
  const pts = v.map((x, i) => [2 + i * (w - 4) / (v.length - 1), h - 3 - (x - lo) / r * (h - 6)]);
  const p = pts.map(q => q[0].toFixed(1) + ',' + q[1].toFixed(1)).join(' ');
  const last = pts[pts.length - 1];
  const area = opts.fill ? `<polygon points="${pts[0][0].toFixed(1)},${h} ${p} ${last[0].toFixed(1)},${h}" fill="${opts.fill}"></polygon>` : '';
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true" style="display:block;overflow:visible">${area}<polyline class="draw" pathLength="1" points="${p}" fill="none" stroke="${color}" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"></polyline><circle cx="${last[0].toFixed(1)}" cy="${last[1].toFixed(1)}" r="2.5" fill="${color}"></circle></svg>`;
}
function seg(id, opts, cur, label) {
  return `<div class="seg" role="group" aria-label="${esc(label)}" data-seg="${id}"><span class="ind" aria-hidden="true"></span>` +
    opts.map(o => `<button type="button" data-set="${id}" data-val="${o[0]}" aria-pressed="${o[0] === cur}">${o[1]}${o[2] != null ? `<span class="ct">${o[2]}</span>` : ''}</button>`).join('') + '</div>';
}
function sh(eb, title, sub, right) {
  return `<div class="sh"><div><div class="eb">${eb}</div><h2>${title}</h2>${sub ? `<p>${sub}</p>` : ''}</div>${right || ''}</div>`;
}
function cu(to, dec, pre, suf) { return `<span data-cu="${to}" data-dec="${dec || 0}" data-pre="${esc(pre || '')}" data-suf="${esc(suf || '')}">${esc(pre || '')}${fin(to, dec || 0)}${esc(suf || '')}</span>`; }

/* ---------- company header ---------- */
const PRICES = [956.1, 1079.85, 1413.4, 1556.2, 1517.7, 1976.7, 2073.7, 2204.2, 2169.2];
const PRL = ['28 Mar 25', '30 Jun 25', '30 Sep 25', '31 Dec 25', '30 Mar 26', '30 Jun 26', '31 Jul 26', '31 Aug 26', '23 Sep 26'];
function companyHeader() {
  const w = S.watch.includes('ANANDRATHI');
  const stats = [['Market cap', cu(Math.round(MCAP), 0, '₹', ' cr'), sgn(100 * (NOW.c / QE.a - 1), 1, '%') + ' since ' + sdate(QE.d), 'overview'], ['P/E (TTM)', (MCAP / TTMP).toFixed(1) + '×', 'TTM PAT ₹' + fin(TTMP, 1) + ' cr', 'overview'], ['P/B', (NOW.c / BVPS).toFixed(1) + '×', 'BVPS ₹' + BVPS.toFixed(1), 'overview'], ['Dividend yield', (100 * DPS / NOW.c).toFixed(2) + '%', 'FY26 DPS ₹' + DPS.toFixed(2) + ' adj.', 'overview'], ['ROE', '46.7%', 'FY26, company-reported', 'overview'], ['Free float', '58.63%', 'Jun-26 filing', 'holders'], ['Shareholders', cu(80729), '+24.3% QoQ', 'overview']];
  const W5 = D.w52, lo = W5.lo, hi = W5.hi, pos = Math.max(0, Math.min(100, (NOW.c - lo) / (hi - lo) * 100));
  const tabs = [['overview', 'Overview'], ['holders', 'Shareholding'], ['flows', 'Buyers &amp; sellers'], ['evidence', 'Evidence &amp; gates']];
  const sparkPts = PRICES.map((p, i) => ({ p, l: PRL[i] }));
  return `<section class="co" aria-label="Company summary"><div class="wrap">
  <div class="crumb"><a href="#universe">Universe</a><span>/</span><span>Financial Services</span><span>/</span><span style="color:var(--ink)">ANANDRATHI</span></div>
  <div class="cohead">
    <div class="coname"><h1>Anand Rathi Wealth Ltd</h1>
      <div class="chips"><span class="chip">NSE: ANANDRATHI</span><span class="chip">BSE: 543415</span><span class="chip">ISIN INE463V01026</span><span class="pill ok">7/7 GATES</span>
      <button class="star" type="button" data-act="watch" data-sym="ANANDRATHI" aria-pressed="${w}"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"></path></svg><span>${w ? 'Watching' : 'Watch'}</span></button></div>
    </div>
    <div class="px">
      <div class="pxs"><small>Daily close, 1 year, bonus-adjusted</small><div class="chart" data-c="price" style="width:200px;height:44px"></div></div>
      <div class="pxv"><span class="big">₹${cu(NOW.c, 2)}</span><span class="chg ${cl(NOW.c - NOW.prev)}">${sgn(NOW.c - NOW.prev, 2)} (${sgn(100 * (NOW.c / NOW.prev - 1), 2, '%')})</span><small>NSE close · ${dfmt(NOW.d)}</small></div>
    </div>
  </div>
  <div class="stats">${stats.map(s => `<a class="stat" href="#${s[3]}"><span class="lbl">${s[0]}</span><span class="v">${s[1]}</span><span class="s">${s[2]}</span></a>`).join('')}
    <div class="stat"><span class="lbl">52-week range</span><div class="range" data-tip="<b>52-week range (intraday)</b><br>Low ₹${fin(lo, 2)} · ${dfmt(W5.lod)}<br>High ₹${fin(hi, 2)} · ${dfmt(W5.hid)}<br>Now ₹${fin(NOW.c, 2)}<br>NSE daily data, bonus-adjusted"><i style="width:${pos.toFixed(1)}%"></i><b style="left:${pos.toFixed(1)}%"></b></div><span class="s num" style="display:flex;justify-content:space-between;width:180px"><span>${fin(lo, 0)}</span><span>${fin(hi, 0)}</span></span></div>
  </div>
  <nav class="tabs" aria-label="Company sections">${tabs.map(t => `<a href="#${t[0]}" data-tab="${t[0]}" ${S.route === t[0] ? 'aria-current="page"' : ''}>${t[1]}</a>`).join('')}<span class="tl" aria-hidden="true"></span></nav>
  </div></section>`;
}

/* ---------- OVERVIEW ---------- */
function ownTable() {
  const u = S.unit;
  let h = `<div class="tscroll"><table class="t"><thead><tr><th class="l" scope="col">Category</th>${T.map(t => `<th scope="col">${t.q}</th>`).join('')}<th scope="col">QoQ</th><th scope="col">6Q Δ</th><th scope="col">Trend</th></tr></thead><tbody>`;
  CATS.forEach(c => {
    const vs = T.map(t => tv(t, c.k, u)), q = vs[5] - vs[4], s6 = vs[5] - vs[0], open = !!S.openCat[c.k];
    h += `<tr><td class="l"><button type="button" data-act="cat" data-k="${c.k}" aria-expanded="${open}" style="display:inline-flex;align-items:center;gap:6px;background:none;border:0;padding:4px 0;cursor:pointer;font-weight:500;min-height:32px"><span class="sw" style="background:${CC[c.k]}"></span>${c.l}<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true" style="transition:transform .3s var(--ease);transform:rotate(${open ? 180 : 0}deg);color:var(--ink3)"><path d="M6 9l6 6 6-6"></path></svg></button></td>` +
      vs.map((v, i) => `<td data-tip="<b>${c.l} · ${T[i].q}</b><br>${(100 * T[i][c.k] / T[i].tot).toFixed(2)}% · ${fin(T[i][c.k] * T[i].bf)} sh (adj.)<br>₹${fin(T[i][c.k] * T[i].px / 1e7)} cr at ₹${fin(T[i].px, 1)}">${fmtU(v, u)}</td>`).join('') +
      `<td class="${cl(q)}" style="font-weight:600">${fmtD(q, u)}</td><td class="${cl(s6)}">${fmtD(s6, u)}</td><td style="width:90px">${spark(vs, 84, 22, CC[c.k])}</td></tr>`;
    if (open) {
      h += `<tr class="sub"><td class="l" style="padding-left:28px">Change vs prior quarter</td><td>—</td>${vs.slice(1).map((v, i) => `<td class="${cl(v - vs[i])}">${fmtD(v - vs[i], u)}</td>`).join('')}<td></td><td></td><td></td></tr>`;
      c.sub.forEach(sb => {
        const sv = T.map(t => tv(t, sb[0], u));
        h += `<tr class="sub swap"><td class="l" style="padding-left:28px">${sb[1]}</td>${sv.map(v => `<td>${fmtU(v, u)}</td>`).join('')}<td class="${cl(sv[5] - sv[4])}">${fmtD(sv[5] - sv[4], u)}</td><td class="${cl(sv[5] - sv[0])}">${fmtD(sv[5] - sv[0], u)}</td><td>${spark(sv, 84, 18, 'var(--ink3)')}</td></tr>`;
      });
      if (c.k !== 'prom') h += `<tr class="sub"><td class="l" style="padding-left:28px" colspan="10"><a href="#${c.k === 'ind' ? 'individuals' : c.k === 'oth' ? 'holders' : c.k}" style="color:var(--acc);font-weight:600;display:inline-flex;gap:6px;align-items:center">${c.k === 'oth' ? 'See named holders' : 'See top holders'} ${arrow}</a></td></tr>`;
    }
  });
  const tl = { pct: 'Total', val: 'Market cap', sh: 'Shares outstanding' }[u], tvs = T.map(t => tv(t, 'tot', u));
  h += `<tr class="tot"><td class="l">${tl}</td>${tvs.map(v => `<td>${fmtU(v, u)}</td>`).join('')}<td class="${u === 'pct' ? '' : cl(tvs[5] - tvs[4])}">${u === 'pct' ? '' : fmtD(tvs[5] - tvs[4], u)}</td><td class="${u === 'pct' ? '' : cl(tvs[5] - tvs[0])}">${u === 'pct' ? '' : fmtD(tvs[5] - tvs[0], u)}</td><td></td></tr>`;
  const nh = T.map(t => t.nh);
  h += `<tr class="sub"><td class="l">Shareholders (count)</td>${nh.map(v => `<td>${fin(v)}</td>`).join('')}<td>${sgn(100 * (nh[5] / nh[4] - 1), 1, '%')}</td><td>${sgn(100 * (nh[5] / nh[0] - 1), 1, '%')}</td><td></td></tr>`;
  return h + '</tbody></table></div>';
}
function ownBody() {
  const cap = { pct: '% of total shares. Tap a category to see its breakdown and quarterly change.', val: '₹ crore at each quarter-end close. Tap a category to see its breakdown.', sh: 'Million shares, adjusted for the Jun-26 1:1 bonus. Tap a category to see its breakdown.' }[S.unit];
  return `<span class="cap">${cap}</span>${ownTable()}<div class="legend">${CATS.map(c => `<span><span class="sw" style="background:${CC[c.k]}"></span>${c.l}</span>`).join('')}</div><div class="chart" data-c="own" style="height:230px"></div>`;
}
const INS = [
  ['PROMOTER · −1.74 PP', 'dn', 'Anand Rathi Financial Services sold 2.89 mn shares', 'Promoter group down to 41.37%, the lowest in six quarters. This sale explains the whole quarterly change: ₹572 cr at the Jun-26 close.', 'flows|A|Anand Rathi Financial Services Ltd'],
  ['DII · +1.29 PP', 'up', 'Domestic institutions at a six-quarter high of 10.39%', 'Insurers rose from 0.21% to 0.93% (Axis Max Life, Bajaj Life, Tata AIA, HDFC Life). Mutual funds hold 9.23%.', 'holders|dii'],
  ['FII · +0.59 PP', 'up', 'Vanguard holds 2.63% alone and added 0.94 mn shares this quarter', 'Named foreign holders cover 63% of FPI shares. The rest sit below disclosure. Norges Bank trimmed in Dec-25.', 'holders|fii|The Vanguard Group'],
  ['BREADTH · +24.3%', 'mut', '80,729 shareholders, up from 64,931', 'The jump came in the quarter of the Jun-26 1:1 bonus. The count was 54,938 at the start of the six quarters.', 'cat|ind']
];
function viewOverview() {
  const L = T[5], P = T[4], pp = k => 100 * L[k] / L.tot - 100 * P[k] / P.tot;
  const pat = `<div class="pbar">${CATS.map((c, i) => `<i style="width:${(100 * L[c.k] / L.tot).toFixed(2)}%;background:${CC[c.k]};animation-delay:${i * 80}ms" data-tip="<b>${c.l}</b><br>${(100 * L[c.k] / L.tot).toFixed(2)}% of shares"></i>`).join('')}</div>
    <div>${CATS.map(c => `<button type="button" class="prow" data-act="catgo" data-k="${c.k}" style="width:100%;background:none;border:0;border-bottom:1px solid var(--rule);cursor:pointer;text-align:left"><span><span class="sw" style="background:${CC[c.k]}"></span>${c.l}</span><span class="num"><b style="font-weight:600">${(100 * L[c.k] / L.tot).toFixed(2)}%</b><span class="${cl(pp(c.k))}" style="display:inline-block;width:72px;text-align:right">${sgn(pp(c.k), 2, ' pp')}</span></span></button>`).join('')}</div>`;
  const ins = `<ul class="ins">${INS.map(x => `<li><button type="button" data-go="${x[4]}" style="display:flex;flex-direction:column;gap:4px;background:none;border:0;padding:0;text-align:left;cursor:pointer;width:100%"><span class="tg ${x[1]}">${x[0]}</span><b>${x[2]}</b><span class="b">${x[3]}</span><span style="font-size:12px;font-weight:600;color:var(--acc);display:inline-flex;gap:6px;align-items:center">View detail ${arrow}</span></button></li>`).join('')}</ul>`;
  const tiles = [['Market cap', cu(Math.round(MCAP), 0, '₹', ' cr'), sgn(100 * (NOW.c / QE.a - 1), 1, '%') + ' since ' + sdate(QE.d), 'Shares ' + (TOT / 1e7).toFixed(2) + ' cr × ₹' + fin(NOW.c, 2)], ['P/E (TTM)', cu(+(MCAP / TTMP).toFixed(1), 1, '', '×'), 'On TTM reported PAT ₹' + fin(TTMP, 1) + ' cr', 'Market cap ₹' + fin(MCAP) + ' cr ÷ PAT of the last four quarters (₹' + TTM.join(' + ') + ' cr)'], ['P/B', cu(+(NOW.c / BVPS).toFixed(1), 1, '', '×'), 'Book value ₹' + BVPS.toFixed(1) + ' per share', 'Mar-26 consolidated equity ≈ ₹999 cr ÷ 166.04 mn shares'], ['Dividend yield', cu(+(100 * DPS / NOW.c).toFixed(2), 2, '', '%'), 'Trailing DPS ₹' + DPS.toFixed(2) + ', bonus-adj.', '₹6 interim (ex 17 Oct 2025) + ₹7 final (ex 15 May 2026), halved for the Jun-26 bonus']];
  return `<div class="g12">
  <section class="card s8" id="own" style="--i:0">${sh('Ownership', 'Ownership trend', 'SEBI shareholding pattern, six filed quarters', seg('unit', [['pct', '% of shares'], ['val', 'Value ₹ cr'], ['sh', 'Shares mn']], S.unit, 'Ownership unit'))}<div id="ownBody">${ownBody()}</div></section>
  <section class="card s4" style="--i:1">${sh('Latest · 30 Jun 2026', 'Pattern and what changed')}${pat}${ins}</section>
  <section class="card s5" style="--i:2">${sh('Valuation', 'Valuation', 'Price ₹' + fin(NOW.c, 2) + ' · ' + dfmt(NOW.d))}<div class="tiles">${tiles.map(t => `<div class="tile" tabindex="0" data-tip="<b>${t[0]}</b><br>${esc(t[3])}"><span class="lbl">${t[0]}</span><span class="v">${t[1]}</span><span class="s">${t[2]}</span></div>`).join('')}</div><span class="lbl" style="text-transform:none;letter-spacing:0;font-size:12px;color:var(--ink2)">Market cap at quarter-end, ₹ crore</span><div class="chart" data-c="mcap" style="height:170px"></div></section>
  <section class="card s7" id="earn" style="--i:3">${sh('Earnings', 'Earnings', 'Consolidated, ₹ crore · six reported quarters', seg('em', [['pat', 'PAT &amp; revenue'], ['eps', 'EPS'], ['mgn', 'Margin']], S.eMetric, 'Earnings chart'))}${earnTable()}<div id="earnBody">${earnBody()}</div><p class="note">Figures as reported in the company's results. Q1 FY27 PAT of ₹163.0 cr includes about ₹110 cr of other income, mostly fair-value gains on investments; the company's adjusted PAT is ₹116 cr, up 24% YoY. Reported EPS for Q4 FY25–Q4 FY26 is on 83.02 mn shares (before the Jun-26 1:1 bonus); Q1 FY27 is reported diluted EPS on 166.04 mn. The last row restates every quarter to 166.04 mn shares so they compare. Q1 FY27 matches the reported ₹9.82.</p></section>
  <section class="card s12" style="--i:4">${sh('Returns', 'Price returns', 'Computed from daily NSE closes · to ' + dfmt(NOW.d), seg('rh', [['1m', '1M'], ['3m', '3M'], ['ytd', 'YTD'], ['1y', '1Y'], ['3y', '3Y ann.']], S.rH, 'Return horizon'))}<div class="g2"><div style="min-width:0">${retTable()}</div><div id="retBody" style="min-width:0">${retBody()}</div></div></section>
  </div>${footer('NSE shareholding patterns (XBRL, SEBI LODR Reg. 31), Mar-25 to Jun-26 · NSE bhavcopy daily closes (stockanalysis.com for 10 Aug–22 Sep 2026, checked against 5 NSE closes) · company results press releases and investor presentations · ' + (LP ? 'Nifty 50 and Nifty 500 closes from NSE\'s daily index files. Prices refresh every trading day from NSE; last close ' + dfmt(NOW.d) + '.' : 'Nifty 50 closes from Business Standard market wraps and Yahoo Finance · Nifty 500 from investing.com and anandrathi.com.') + ' Values are shares × NSE close at quarter end (28 Mar 2025 for Mar-25).')}`;
}
const EQ = ['Q4 FY25', 'Q1 FY26', 'Q2 FY26', 'Q3 FY26', 'Q4 FY26', 'Q1 FY27'], EQd = ['Mar-25', 'Jun-25', 'Sep-25', 'Dec-25', 'Mar-26', 'Jun-26'];
const REV = D.earn.rev, PAT = D.earn.pat, EPSR = D.earn.eps_rep, EPS = PAT.map(p => p * 1e7 / TOT);
function earnTable() {
  const row = (lab, vs, f, bold, yoy, suf) => `<tr><td class="l" style="font-weight:${bold ? 600 : 500}">${lab}</td>${vs.map((v, i) => `<td style="font-weight:${bold && i === 5 ? 600 : 400}">${f(v)}</td>`).join('')}<td class="${cl(yoy)}" style="font-weight:600">${yoy == null ? '<span class="mut" title="Share basis changed">n.m.</span>' : sgn(yoy, 1, suf || '%')}</td></tr>`;
  return `<div class="tscroll"><table class="t"><thead><tr><th class="l" scope="col">₹ crore</th>${EQ.map((q, i) => `<th scope="col"><span style="display:block">${q}</span><span style="display:block;font-weight:400;letter-spacing:0;text-transform:none">${EQd[i]}</span></th>`).join('')}<th scope="col">YoY</th></tr></thead><tbody>
  ${row('Revenue from ops', REV, v => fin(v, 2), false, 100 * (REV[5] / REV[1] - 1))}${row('PAT (reported)', PAT, v => fin(v, 2), true, 100 * (PAT[5] / PAT[1] - 1))}${row('PAT margin', PAT.map((p, i) => 100 * p / REV[i]), v => v.toFixed(1) + '%', false, 100 * PAT[5] / REV[5] - 100 * PAT[1] / REV[1], ' pp')}${row('EPS as reported (₹)', EPSR, v => v.toFixed(2), false, null)}${row('EPS on 166.04 mn shares (₹)', EPS, v => v.toFixed(2), true, 100 * (EPS[5] / EPS[1] - 1))}</tbody></table></div>`;
}
function earnBody() {
  const leg = S.eMetric === 'pat' ? `<span><span class="sw" style="background:var(--rev)"></span>Revenue</span><span><span class="sw" style="background:var(--ink)"></span>PAT</span>` : S.eMetric === 'eps' ? `<span><span class="sw" style="background:var(--ink)"></span>EPS, ₹ on 166.04 mn shares</span>` : `<span><span class="sw" style="background:var(--ink)"></span>PAT margin, %</span>`;
  return `<div class="legend">${leg}</div><div class="chart" data-c="earn" style="height:210px"></div>`;
}
const RP = [['1m', '1 month', '2026-08-21', null], ['3m', '3 months', '2026-06-23', null], ['6m', '6 months', '2026-03-24', null], ['ytd', 'Year to date', '2025-12-31', null], ['1y', '1 year', '2025-09-23', null], ['3y', '3 years, annualised', '2023-09-22', 3], ['sl', 'Since listing, annualised', '2021-12-14', (Date.UTC(2026, 8, 23) - Date.UTC(2021, 11, 14)) / 864e5 / 365.25]];
const LAST = '2026-09-23';
function rcalc(a, b, yrs) { if (a == null || b == null) return null; const r = a / b - 1; return 100 * (yrs ? Math.pow(1 + r, 1 / yrs) - 1 : r); }
// Return bases: from prices.js when live (rolling with the latest close), else the snapshot's fixed anchors.
const RB = LP ? LP.bases : RP.map(p => { const sa = D.stock_anchor[p[2]]; return { k: p[0], l: p[1], d: sa[0], s: sa[1], sraw: sa[2], ssrc: sa[3], n50: D.bench.nifty50[p[2]], n500: D.bench.nifty500[p[2]], yrs: p[3] }; });
const RET = RB.map(b => {
  const ov = LP ? null : (D.bench.override.nifty500 || {})[b.k];
  const n500 = b.n500 != null ? rcalc(NOW.n500, b.n500, b.yrs) : (ov ? ov[0] : null);
  return { k: b.k, l: b.l, base: b.d, s: rcalc(NOW.c, b.s, b.yrs), sraw: b.sraw, ssrc: b.ssrc, n50: rcalc(NOW.n50, b.n50, b.yrs), n50b: b.n50, n500, n500b: b.n500, n500src: b.n500 != null ? 'close ' + fin(b.n500, 2) + ' → ' + fin(NOW.n500, 2) : ov ? ov[1] : null };
});
function retTable() {
  const f = (v, tip) => v == null ? `<span class="mut" data-tip="${esc(tip)}">n/a</span>` : `<span ${tip ? `data-tip="${esc(tip)}"` : ''}>${sgn(v, 2, '%')}</span>`;
  return `<div class="tscroll"><table class="t"><thead><tr><th class="l" scope="col">Period</th><th class="l" scope="col">From</th><th scope="col">ANANDRATHI</th><th scope="col">Nifty 50</th><th scope="col">Nifty 500</th><th scope="col">vs Nifty 50</th></tr></thead><tbody>${RET.map(r => { const ex = r.n50 == null ? null : r.s - r.n50; return `<tr><td class="l" style="font-weight:500">${r.l}</td><td class="l mut">${dfmt(r.base)}</td><td class="${cl(r.s)}" style="font-weight:600">${f(r.s, 'Close ₹' + fin(r.sraw, 2) + ' on ' + dfmt(r.base) + (r.sraw !== r.s ? ' (bonus-adjusted base)' : '') + ' → ₹' + fin(NOW.c, 2) + ' · ' + r.ssrc)}</td><td class="${cl(r.n50)}">${f(r.n50, 'Nifty 50 ' + fin(r.n50b, 2) + ' → ' + fin(NOW.n50, 2))}</td><td class="${cl(r.n500)}">${f(r.n500, r.n500 == null ? 'No Nifty 500 close on file for ' + dfmt(r.base) : 'Nifty 500 · ' + r.n500src)}</td><td class="${cl(ex)}" style="font-weight:600">${ex == null ? '<span class="mut">n/a</span>' : sgn(ex, 1, ' pp')}</td></tr>`; }).join('')}</tbody></table></div><p class="cap" style="margin:10px 0 0">Price returns, dividends excluded, to the ${dfmt(NOW.d)} close. Stock bases are NSE closes adjusted for the two 1:1 bonuses. Hover or tap a figure for its inputs.${RET.some(r => r.n500 == null) ? ' Cells without a verified Nifty 500 close show n/a.' : ''}</p>`;
}
function retBody() {
  const r = RET.find(x => x.k === S.rH) || RET[4];
  const items = [['ANANDRATHI', r.s, 'var(--ink)'], ['Nifty 50', r.n50, 'var(--grey)'], ['Nifty 500', r.n500, 'var(--rev)']];
  const mx = Math.max.apply(null, items.map(x => Math.abs(x[1] || 0))) || 1;
  return `<div style="display:flex;flex-direction:column;gap:14px;padding-top:6px">${items.map((x, i) => { if (x[1] == null) return `<div style="display:grid;grid-template-columns:96px 1fr 70px;gap:10px;align-items:center;font-size:13px"><span style="color:var(--ink2)">${x[0]}</span><span class="cap">No verified close for ${dfmt(r.base)}</span><span class="mut" style="text-align:right">n/a</span></div>`; const w = Math.abs(x[1]) / mx * 50; return `<div style="display:grid;grid-template-columns:96px 1fr 70px;gap:10px;align-items:center;font-size:13px"><span style="color:var(--ink2)">${x[0]}</span><div style="position:relative;height:18px"><div style="position:absolute;left:50%;top:-4px;bottom:-4px;width:1px;background:var(--ink)"></div><div class="hb ${x[1] < 0 ? 'neg' : ''}" style="--i:${i};position:absolute;top:0;height:18px;width:${w.toFixed(1)}%;${x[1] >= 0 ? 'left:50%' : 'right:50%'};background:${x[2]}"></div></div><span class="num ${cl(x[1])}" style="font-weight:600;text-align:right">${sgn(x[1], 1, '%')}</span></div>`; }).join('')}<span class="cap">${r.l} · from ${dfmt(r.base)}. Bars share one scale, centred on zero.</span></div>`;
}

/* ---------- HOLDERS ---------- */
function viewHolders() {
  const f20 = D.fii.reduce((a, h) => a + h.s[5], 0);
  const k = [['fii', 'FII / FPI · Jun-26 filing', '6.37%', '127 FPI accounts. Named holders cover 63% of FPI shares.'], ['dii', 'DII · Jun-26 filing', '10.39%', 'Mutual funds 9.23% · insurers 0.93% · AIFs 0.24%'], ['fii', 'Top 2 foreign holders', ((D.fii[0].s[5] + D.fii[1].s[5]) / TOT * 100).toFixed(2) + '%', 'Vanguard ' + (D.fii[0].s[5] / TOT * 100).toFixed(2) + '% + BlackRock ' + (D.fii[1].s[5] / TOT * 100).toFixed(2) + '%'], ['dii', 'Top 2 domestic holders', ((D.dii[0].s[5] + D.dii[1].s[5]) / TOT * 100).toFixed(2) + '%', 'Quant MF + SBI MF, mostly small-cap schemes']];
  return `<div class="kpis" style="--i:0">${k.map(x => `<button type="button" class="kpi" data-set="hTab" data-val="${x[0]}" style="text-align:left;cursor:pointer"><span class="lbl">${x[1]}</span><span class="v">${x[2]}</span><span class="s">${x[3]}</span></button>`).join('')}</div>
  <section class="card" id="hCard" style="--i:1;margin-top:24px">${holdersHead()}<div id="hBody">${holdersBody()}</div></section>
  ${footer('holdermap run of 23 Sep 2026 on the Bloomberg Security Ownership export (ANANDRAT IN), reconciled to NSE shareholding filings (7/7 gates). Categories come from SEBI Table II/III, AMFI, IRDAI, SEC registries and GLEIF. Shares are restated for the Jun-26 1:1 bonus. Free float = total shares minus the promoter group in that quarter\'s filing.')}`;
}
function holdersHead() {
  const title = { fii: 'Top 20 FIIs', dii: 'Top 20 DIIs', ind: 'Top individual holdings' }[S.hTab];
  const sub = { fii: 'Every foreign holder Bloomberg names with a position today, ranked by shares', dii: 'Mutual funds and insurers, grouped at fund-house level', ind: '16 individuals and family trusts named in SEBI filings: the full promoter group plus public holders above 1%' }[S.hTab];
  return sh('Shareholding', title, sub, seg('hTab', [['fii', 'FIIs', D.fii.length], ['dii', 'DIIs', D.dii.length], ['ind', 'Individuals', D.ind.length]], S.hTab, 'Holder group'));
}
function holdersBody() {
  const L = GROUPS[S.hTab].slice(), b = S.basis, q = S.hTab === 'ind' ? 4 : 5;
  const st = new Map(L.map(h => [h, hStats(h, b)]));
  const key = { n: h => h.n.toLowerCase(), cty: h => h.cty, s: h => st.get(h).sh, v: h => st.get(h).v, pt: h => st.get(h).pt, pff: h => st.get(h).pff == null ? -1 : st.get(h).pff, mean: h => st.get(h).mean || 0, mx: h => st.get(h).mx || 0, mn: h => st.get(h).mn || 0, d: h => st.get(h).d }[S.hSort] || (h => st.get(h).sh);
  L.sort((a, c) => { const x = key(a), y = key(c); return (x > y ? 1 : x < y ? -1 : 0) * S.hDir; });
  const asof = S.hTab === 'ind' ? 'Q2/2026 · filing of 30 Jun 2026 · value at ₹1,976.70' : 'Q3/2026 to date · Bloomberg, 22 Sep 2026 · value at ₹' + fin(OQ.c, 2) + ' (' + dfmt(OQ.d) + ')';
  const sortBtn = (k, lab, cls) => `<span class="${cls || ''}"><button type="button" data-sort="h" data-k="${k}" ${S.hSort === k ? `aria-sort="${S.hDir > 0 ? 'ascending' : 'descending'}"` : ''}>${lab}${S.hSort === k ? (S.hDir > 0 ? ' ↑' : ' ↓') : ''}</button></span>`;
  const qlab = S.hTab === 'ind' ? '5Q' : '6Q';
  let h = `<div class="frow"><div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">${seg('basis', [['pct', '% of total'], ['ff', '% of free float'], ['val', 'Value ₹ cr']], b, 'Metric basis')}
    <label class="pm2" style="display:flex;gap:8px;align-items:center;font-size:12px;font-weight:600;color:var(--ink2)">Sort <select class="field" id="hSortSel" data-sortsel="h">${[['s', 'Shares'], ['v', 'Value'], ['pt', '% total'], ['d', 'QoQ change'], ['mean', 'Mean'], ['n', 'Name']].map(o => `<option value="${o[0]}" ${S.hSort === o[0] ? 'selected' : ''}>${o[1]}</option>`).join('')}</select></label></div>
    <span class="cap"><b style="color:var(--ink);font-weight:600">As of</b> ${asof}</span></div>
    <div class="legend" style="color:var(--ink3)"><span><span class="flag" style="margin:0 8px 0 0"></span>Category flagged for review</span><span>Trend, mean, max and min use ${unitB[b]} across ${qlab === '6Q' ? 'Jun-25 to Sep-26' : 'Jun-25 to Jun-26'}. Tap a row for quarter-by-quarter detail.</span></div>
    <div role="table" aria-label="${esc(S.hTab)} holders"><div class="lhead gH" role="row"><span class="l">#</span>${sortBtn('n', 'Holder', 'l')}${sortBtn('cty', 'Cty', 'l')}${sortBtn('s', 'Shares mn')}${sortBtn('v', 'Value ₹ cr')}${sortBtn('pt', '% total')}${sortBtn('pff', '% FF')}<span>${qlab} trend</span>${sortBtn('mean', 'Mean', 'xm')}${sortBtn('mx', 'Max', 'xm')}${sortBtn('mn', 'Min', 'xm')}${sortBtn('d', 'QoQ Δ')}<span></span></div>`;
  L.forEach((x, i) => {
    const s = st.get(x);
    const pm = b === 'val' ? `₹${fin(s.v, 1)} cr` : b === 'ff' ? (s.pff == null ? '—' : s.pff.toFixed(3) + '%') : s.pt.toFixed(3) + '%';
    h += `<div class="lrow" data-row="${x.id}" style="--i:${Math.min(i, 20)}"><button type="button" class="rb gH" data-act="row" aria-expanded="false">
      <span class="rk">${x.rank}</span>
      <span class="l" style="min-width:0"><span class="nm">${esc(x.n)}${x.rv ? '<span class="flag" aria-label="Flagged for review"></span>' : ''}</span><span class="sb">${esc(x.sub)}${x.ow ? ' · ' + esc(x.ow) : ''}${x.note ? ' · ' + esc(x.note) : ''}<span class="pm2"> · ${x.cty}</span></span></span>
      <span class="l xp"><span class="chip" title="${CTY[x.cty] || x.cty}">${x.cty}</span></span>
      <span class="xp">${(s.sh / 1e6).toFixed(3)}</span><span class="xp">${fin(s.v, 1)}</span><span class="xp" style="font-weight:600">${s.pt.toFixed(3)}%</span><span class="xp">${s.pff == null ? '—' : s.pff.toFixed(3) + '%'}</span>
      <span class="xp" style="justify-self:end">${spark(s.vals, 92, 22, x.c === 'Promoter' ? 'var(--prom)' : 'var(--ink)')}</span>
      <span class="xp xm mut">${fmtB(s.mean, b)}</span><span class="xp xm mut">${fmtB(s.mx, b)}</span><span class="xp xm mut">${fmtB(s.mn, b)}</span>
      <span class="xp ${cl(s.d)}" style="font-weight:500">${s.d ? sgnI(s.d) : '0'}</span>
      <span class="pm2" style="display:flex;flex-direction:column;align-items:flex-end"><b style="font-weight:600">${pm}</b><span class="${cl(s.d)}" style="font-size:11px">${s.d ? sgnI(s.d) : 'no change'}</span></span>
      ${chev}</button><div class="det"><div></div></div></div>`;
  });
  const tS = L.reduce((a, x) => a + st.get(x).sh, 0), tV = L.reduce((a, x) => a + st.get(x).v, 0);
  h += `<div class="ltot gH"><span class="xp"></span><span class="l">${S.hTab === 'ind' ? 'All ' + L.length + ' combined' : 'Top ' + L.length + ' combined'}</span><span class="xp"></span><span class="xp">${(tS / 1e6).toFixed(3)}</span><span class="xp">${fin(tV, 1)}</span><span class="xp">${(100 * tS / TOT).toFixed(3)}%</span><span class="xp">${S.hTab === 'ind' ? '' : (100 * tS / FF[q]).toFixed(3) + '%'}</span><span class="xp"></span><span class="xp xm"></span><span class="xp xm"></span><span class="xp xm"></span><span class="xp"></span><span class="pm pm2">${(100 * tS / TOT).toFixed(2)}% · ₹${fin(tV)} cr</span><span class="xp"></span></div></div>`;
  if (S.hTab === 'fii') h += `<p class="note grey">These 20 names hold ${(100 * D.fii.reduce((a, x) => a + x.s[4], 0) / D.fii_total).toFixed(0)}% of FPI shares at Jun-26. The rest are funds below Bloomberg's disclosure line.</p>`;
  if (S.hTab === 'ind') h += `<p class="note grey">Individuals appear only in quarterly filings. The open quarter updates once the Sep-26 pattern is filed (due by 21 Oct).</p>`;
  return h;
}
function holderDetail(x) {
  const n = x.g === 'ind' ? 5 : 6, qs = HQ.slice(0, n), s = hStats(x, S.basis);
  const rows = qs.map((q, i) => ({ q, sh: x.s[i] || 0, pt: 100 * (x.s[i] || 0) / TOT, pff: x.c === 'Promoter' ? null : 100 * (x.s[i] || 0) / FF[i], v: (x.s[i] || 0) * PX[i] / 1e7 }));
  const inFlow = ['A', 'B'].some(p => D.flows[p].all.some(f => f.n === x.n));
  const mx = Math.max.apply(null, rows.map(r => r.sh)) || 1;
  const bars = `<div style="display:flex;gap:8px;align-items:flex-end;height:120px">${rows.map((r, i) => `<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:4px;justify-content:flex-end;height:100%" data-tip="<b>${r.q}</b><br>${fin(r.sh)} shares<br>${r.pt.toFixed(3)}% of total${r.pff != null ? ' · ' + r.pff.toFixed(3) + '% FF' : ''}<br>₹${fin(r.v, 1)} cr"><span style="font-size:10px;color:var(--ink2)" class="num">${(r.sh / 1e6).toFixed(2)}</span><div class="bar" style="--i:${i};width:100%;max-width:44px;height:${Math.max(2, r.sh / mx * 80).toFixed(0)}px;background:${i === n - 1 ? 'var(--acc)' : 'var(--ink)'}"></div><span style="font-size:10px;color:var(--ink3)">${r.q}</span></div>`).join('')}</div>`;
  return `<div class="detin">
    <div class="k"><span class="lbl">Shares</span><b>${fin(s.sh)}</b></div>
    <div class="k"><span class="lbl">Value</span><b>₹${fin(s.v, 1)} cr</b></div>
    <div class="k"><span class="lbl">% of total</span><b>${s.pt.toFixed(3)}%</b></div>
    <div class="k"><span class="lbl">% of free float</span><b>${s.pff == null ? '— (promoter)' : s.pff.toFixed(3) + '%'}</b></div>
    <div class="k"><span class="lbl">Mean · Max · Min</span><b style="font-size:13px">${fmtB(s.mean, S.basis)} · ${fmtB(s.mx, S.basis)} · ${fmtB(s.mn, S.basis)}</b><span class="cap">${unitB[S.basis]}</span></div>
    <div class="k"><span class="lbl">Country · type</span><b style="font-size:13px">${CTY[x.cty] || x.cty} · ${esc(x.sub)}</b></div>
    <div class="wide"><span class="lbl">Shares by quarter, million</span>${bars}</div>
    ${x.rv ? `<div class="wide note">Category is <b>${esc(x.c)}</b> by default. The alternative on file is <b>${esc(x.alt || 'none')}</b>. <a href="#evidence" style="color:var(--acc);font-weight:600">Open the review queue</a></div>` : ''}
    ${inFlow ? `<div class="wide"><button type="button" class="btn" data-go="flows|${D.flows.A.all.some(f => f.n === x.n) ? 'A' : 'B'}|${esc(x.n)}">See this holder's trades ${arrow}</button></div>` : ''}
  </div>`;
}

/* ---------- FLOWS ---------- */
const GRP = c => c === 'Promoter' ? 'prom' : ['Foreign AMC', 'Foreign Government', 'Foreign Insurance', 'Foreign corporate', 'Bank'].includes(c) ? 'fii' : ['Domestic AMC', 'Domestic Insurance', 'Domestic Pension Fund', 'Government'].includes(c) ? 'dii' : 'ind';
const GL = { prom: 'Promoter group', fii: 'Foreign institutions', dii: 'Domestic institutions', ind: 'Individuals & corporates' };
function viewFlows() {
  return `<div class="frow" style="--i:0">${seg('fP', [['A', 'Q2/26 vs Q1/26 · filed'], ['B', 'Q3/26 to date · live']], S.fP, 'Comparison period')}<span class="cap">Holder level, from the Bloomberg export reconciled to filings · shares restated for the Jun-26 bonus</span></div>
  <div id="fBody" style="--i:1;margin-top:20px">${flowsBody()}</div>
  ${footer('Buyer or seller = change in shares between two quarter-ends. NEW = no position in the earlier quarter; EXIT = none now. The Anandrathi Housing Finance line is left out: it is the same entity as Twelfth Tier Property, renamed (MCA master data).')}`;
}
function flowsBody() {
  const F = D.flows[S.fP], px = S.fP === 'A' ? '₹1,976.70 (30 Jun 2026)' : '₹' + fin(OQ.c, 2) + ' (' + dfmt(OQ.d) + ')';
  const agg = { prom: 0, fii: 0, dii: 0, ind: 0 }, cnt = { prom: [0, 0], fii: [0, 0], dii: [0, 0], ind: [0, 0] };
  F.all.forEach(o => { const g = GRP(o.c); agg[g] += o.v; cnt[g][o.d > 0 ? 0 : 1]++; });
  const mx = Math.max.apply(null, Object.values(agg).map(Math.abs)) || 1;
  const net = Object.keys(GL).map((g, i) => { const v = agg[g], w = Math.abs(v) / mx * 50, on = S.fG === g; return `<button type="button" class="netrow" data-act="fgrp" data-g="${g}" aria-pressed="${on}" style="background:${on ? 'var(--surface2)' : 'none'};border-left:3px solid ${on ? 'var(--acc)' : 'transparent'}"><span><b style="font-weight:600;display:block">${GL[g]}</b><span class="cap">${cnt[g][0]} buying · ${cnt[g][1]} selling</span></span><div class="nb"><div style="position:absolute;left:50%;top:-4px;bottom:-4px;width:1px;background:var(--ink)"></div><div class="hb ${v < 0 ? 'neg' : ''}" style="--i:${i};position:absolute;top:0;height:18px;width:${w.toFixed(1)}%;${v >= 0 ? 'left:50%' : 'right:50%'};background:${v >= 0 ? 'var(--up)' : 'var(--dn)'}"></div></div><span class="num ${cl(v)}" style="font-weight:600;text-align:right">${sgn(v, 1)} cr</span></button>`; }).join('');
  const filt = L => S.fG ? L.filter(o => GRP(o.c) === S.fG) : L;
  const buy = filt(S.fG ? F.all.filter(o => o.d > 0).sort((a, b) => b.d - a.d).slice(0, 25) : F.buy), sell = filt(S.fG ? F.all.filter(o => o.d < 0).sort((a, b) => a.d - b.d).slice(0, 25) : F.sell);
  const noteB = S.fP === 'B' ? `<p class="note grey">Five filing-only holders (Amit Rathi, Supriya Saigal, Fahim Sultan Ali, Suhas Gupta Family Trust and Munix India) read 0 in Bloomberg's open quarter. They are held back until the Sep-26 filing confirms an actual exit.</p>` : '';
  const chip = S.fG ? `<button type="button" class="fchip" data-act="fgrp" data-g="${S.fG}" aria-pressed="true">Showing ${GL[S.fG]} <span aria-hidden="true">✕</span></button>` : '';
  return `<div class="g12"><section class="card s12">${sh('Net flow', 'Net flow by holder type', (S.fP === 'A' ? 'Mar-26 → Jun-26' : 'Jun-26 → 22 Sep 2026') + ' · value of the change at ' + px + '. Tap a type to filter the lists.', chip)}<div style="display:flex;flex-direction:column;gap:4px">${net}</div>${noteB}</section>
  <section class="card s6">${sh('Buyers', 'Top 25 buyers', buy.length + ' shown' + (S.fG ? ' · ' + GL[S.fG] : ''))}${flowList(buy, true)}</section>
  <section class="card s6">${sh('Sellers', 'Top 25 sellers', sell.length + ' shown' + (S.fG ? ' · ' + GL[S.fG] : ''))}${flowList(sell, false)}</section></div>`;
}
function flowList(L, buy) {
  if (!L.length) return `<p class="cap" style="padding:16px 0">No ${buy ? 'buyers' : 'sellers'} in this group for the period.</p>`;
  let h = `<div><div class="lhead gF"><span class="l">#</span><span class="l">Holder</span><span>Δ shares</span><span>Δ ₹ cr</span><span>Δ pp</span><span>Now mn</span><span></span></div>`;
  L.forEach((x, i) => {
    const tag = x.t ? `<span class="tag ${buy ? 'b' : 's'}" style="margin-left:8px">${x.t.toUpperCase()}</span>` : '';
    h += `<div class="lrow" data-row="${slug(x.n)}" data-flow="1" style="--i:${Math.min(i, 20)}"><button type="button" class="rb gF" data-act="frow" aria-expanded="false"><span class="rk">${i + 1}</span><span class="l" style="min-width:0"><span class="nm">${esc(x.n)}</span><span class="sb">${x.t ? tag.replace('margin-left:8px', 'margin-right:6px') : ''}${esc(x.sub)} · ${x.cty}</span></span><span class="xp ${buy ? 'up' : 'dn'}" style="font-weight:600">${sgnI(x.d)}</span><span class="xp">${sgn(x.v, 1)}</span><span class="xp mut">${sgn(100 * x.d / TOT, 3)}</span><span class="xp">${(x.a / 1e6).toFixed(3)}</span><span class="pm2" style="display:flex;flex-direction:column;align-items:flex-end"><b class="${buy ? 'up' : 'dn'}" style="font-weight:600">${sgnI(x.d)}</b><span style="font-size:11px;color:var(--ink3)">${sgn(x.v, 1)} cr</span></span>${chev}</button><div class="det"><div></div></div></div>`;
  });
  return h + '</div>';
}
function flowDetail(name) {
  const x = D.flows[S.fP].all.find(o => o.n === name); if (!x) return '';
  const h = findHolder(x.n);
  const pc = x.b ? 100 * x.d / x.b : null;
  return `<div class="detin"><div class="k"><span class="lbl">Before</span><b>${fin(x.b)}</b></div><div class="k"><span class="lbl">After</span><b>${fin(x.a)}</b></div><div class="k"><span class="lbl">Change</span><b class="${cl(x.d)}">${pc == null ? 'New position' : sgn(pc, 1, '%')}</b></div><div class="k"><span class="lbl">Δ % of total</span><b>${sgn(100 * x.d / TOT, 3, ' pp')}</b></div><div class="k"><span class="lbl">Category</span><b style="font-size:13px">${esc(x.c)}</b></div>
  ${h ? `<div class="wide"><button type="button" class="btn" data-go="holders|${h.g}|${esc(h.n)}">Open in shareholding ${arrow}</button></div>` : `<div class="wide cap">Not in the current top-20 holder lists.</div>`}</div>`;
}

/* ---------- EVIDENCE ---------- */
const TN = { 'T1-filing': 'T1 · SEBI filing', 'T2-registry': 'T2 · Official registry', 'T3-rule': 'T3 · Legal-form rule', 'override': 'Override, with reason' };
const TC = { 'T1-filing': 'var(--ink)', 'T2-registry': 'var(--dii)', 'T3-rule': 'var(--fii)', 'override': 'var(--acc)' };
function viewEvidence() {
  const tot = Object.values(D.tiers).reduce((a, b) => a + b, 0);
  const k = [['Gates', '7 / 7', 'All passed · run of ' + D.gen.replace('T', ', ').slice(0, 17), 'up'], ['Holders categorised', '102', '0 unresolved · 0 invalid categories', ''], ['Holder-quarters reconciled', '106', '0 mismatches against filed share counts', ''], ['Flagged for review', String(D.flag.length), 'Default kept, alternative recorded', 'dn']];
  const gates = `<div class="tscroll"><table class="t"><thead><tr><th class="l">#</th><th class="l">Gate</th><th class="l">Result</th><th>Status</th></tr></thead><tbody>${D.gates.map((g, i) => `<tr><td class="l mut" style="width:24px">${i + 1}</td><td class="l" style="font-weight:500;white-space:normal;min-width:160px">${esc(g.n[0].toUpperCase() + g.n.slice(1))}</td><td class="l" style="white-space:normal;color:var(--ink2);min-width:220px">${esc(g.d)}</td><td><span class="pill ok">PASS</span></td></tr>`).join('')}</tbody></table></div>`;
  const tiers = `<div class="pbar">${Object.keys(D.tiers).map((t, i) => `<i style="width:${(100 * D.tiers[t] / tot).toFixed(2)}%;background:${TC[t]};animation-delay:${i * 90}ms" data-tip="<b>${TN[t]}</b><br>${D.tiers[t]} holders"></i>`).join('')}</div><div>${Object.keys(D.tiers).map(t => `<div class="prow"><span><span class="sw" style="background:${TC[t]}"></span>${TN[t]}</span><span class="num"><b style="font-weight:600">${D.tiers[t]}</b><span class="mut" style="margin-left:10px">${Math.round(100 * D.tiers[t] / tot)}%</span></span></div>`).join('')}</div>`;
  const rec = `<div class="tscroll"><table class="t"><thead><tr><th class="l">Category · Jun-26</th><th>Holder sum</th><th>Filing total</th><th>Ratio</th><th>Band</th></tr></thead><tbody>${D.rec.map(r => `<tr><td class="l" style="white-space:normal;min-width:220px"><b style="font-weight:500">${esc(r.c[0].toUpperCase() + r.c.slice(1))}</b><span style="display:block;font-size:11px;color:var(--ink3);line-height:1.4;margin-top:2px">${esc(r.note)}</span></td><td>${fin(r.b)}</td><td>${fin(r.f)}</td><td style="font-weight:600">${r.r.toFixed(3)}</td><td class="mut">${r.band}</td></tr>`).join('')}</tbody></table></div>`;
  const pr = `<div class="tscroll"><table class="t"><thead><tr><th class="l">Quarter</th><th class="l">Trade date</th><th>Close ₹</th><th>Bonus</th><th>Adj. ₹</th></tr></thead><tbody>${D.prices.map(p => `<tr ${p.note ? `data-tip="${esc(p.note)}"` : ''}><td class="l" style="font-weight:500">${p.q}</td><td class="l mono" style="font-size:12px">${p.d}</td><td>${fin(p.c, 2)}</td><td>${p.f.toFixed(1)}×</td><td>${fin(p.a, 2)}</td></tr>`).join('')}</tbody></table></div>`;
  return `<div class="kpis" style="--i:0">${k.map(x => `<div class="kpi"><span class="lbl">${x[0]}</span><span class="v ${x[3]}">${x[1]}</span><span class="s">${x[2]}</span></div>`).join('')}</div>
  <div class="g12" style="margin-top:24px">
  <section class="card s7" style="--i:1">${sh('Gates', 'Reconciliation gates', 'Every run must pass all seven before it is published')}${gates}</section>
  <section class="card s5" style="--i:2">${sh('Provenance', 'How each holder was categorised', '102 rows, by evidence tier')}${tiers}</section>
  <section class="card s7" style="--i:3">${sh('Category sums', 'Holder sums vs filing totals', 'Gate 3 detail · quarter Q2/2026')}${rec}</section>
  <section class="card s5" style="--i:4">${sh('Prices', 'Quarter-end prices', 'Value = restated shares × adjusted close')}${pr}</section>
  <section class="card s12" id="rq" style="--i:5">${sh('Review queue', 'Analyst review', 'Rows where the category rests on a registry match or a rule, not a filing. Decisions are saved in this browser.', `<button type="button" class="btn" data-act="rvreset">Reset decisions</button>`)}<div id="rqBody">${reviewBody()}</div></section>
  </div>${footer('Source: holdermap run record ANANDRATHI_run.json. Every row\'s evidence sentence and source URL is in the workbook\'s Evidence sheet.')}`;
}
function reviewBody() {
  const done = D.flag.filter(f => S.review[f.n]).length;
  return `<div style="display:flex;justify-content:space-between;align-items:center;gap:12px;font-size:12px;color:var(--ink2)"><span><b style="color:var(--ink)">${done}</b> of ${D.flag.length} reviewed</span></div><div class="progress"><i style="width:${(100 * done / D.flag.length).toFixed(1)}%"></i></div>
  <div><div class="rv h"><span>Holder</span><span>Default</span><span>Alternative</span><span>Tier</span><span style="text-align:right">Shares now</span><span style="text-align:right">Decision</span></div>
  ${D.flag.map(f => { const r = S.review[f.n]; return `<div class="rv"><span style="font-weight:500">${esc(f.n)}</span><span class="c2">${esc(f.c)}</span><span class="c3" style="color:var(--acc)">${esc(f.alt || '—')}</span><span class="c4 mono" style="font-size:12px;color:var(--ink3)">${esc(f.tier)}</span><span class="c5 num" style="text-align:right">${fin(f.sh)}</span><span class="acts">${r ? `<span class="done ${r === 'keep' ? 'up' : ''}" style="${r === 'switch' ? 'color:var(--acc)' : ''}">${r === 'keep' ? '✓ Kept ' + esc(f.c) : '→ ' + esc(f.alt || f.c)}</span><button type="button" class="btn" data-act="rv" data-n="${esc(f.n)}" data-v="">Undo</button>` : `<button type="button" class="btn" data-act="rv" data-n="${esc(f.n)}" data-v="keep">Keep</button>${f.alt ? `<button type="button" class="btn pri" data-act="rv" data-n="${esc(f.n)}" data-v="switch">Switch</button>` : ''}`}</span></div>`; }).join('')}</div>`;
}

/* ---------- UNIVERSE ---------- */
const BK = m => m >= 500000 ? 'mega' : m >= 100000 ? 'large' : 'mid';
function uList() {
  const q = S.uQ.trim().toLowerCase();
  let L = D.univ.filter(u => (S.uB === 'all' || (S.uB === 'watch' ? S.watch.includes(u.s) : BK(u.m) === S.uB)) && (!q || u.n.toLowerCase().includes(q) || u.s.toLowerCase().includes(q)));
  const key = { m: u => u.m, p: u => u.p, q: u => u.q == null ? -999 : u.q, pr: u => u.pr, fi: u => u.fi || 0, di: u => u.di || 0, h: u => u.h, n: u => u.n.toLowerCase(), ok: u => u.ok ? 1 : 0 }[S.uSort];
  L.sort((a, b) => { const x = key(a), y = key(b); return (x > y ? 1 : x < y ? -1 : 0) * S.uDir; });
  return L;
}
function viewUniverse() {
  const cnt = { mega: 0, large: 0, mid: 0 }; D.univ.forEach(u => cnt[BK(u.m)]++);
  const pins = S.watch.map(s => D.univ.find(u => u.s === s)).filter(Boolean);
  const pinHtml = pins.map(u => {
    const ar = u.s === 'ANANDRATHI';
    return `<${ar ? 'a href="#overview"' : `button type="button" data-act="sheet" data-sym="${u.s}"`} class="pin" style="text-align:left;width:100%;box-sizing:border-box;cursor:pointer;font:inherit;color:inherit">
    <div style="display:flex;flex-direction:column;gap:3px;min-width:0"><span class="mono" style="font-size:10px;letter-spacing:.08em;color:var(--acc)">WATCHLIST</span><span class="serif" style="font-size:20px;font-weight:600;line-height:1.2">${esc(u.n)}</span><span class="mono" style="font-size:11px;color:var(--ink3)">${u.s} · rank ${D.univ.indexOf(u) + 1} of ${D.univ.length} by mcap</span></div>
    <div><span class="lbl">Mkt cap</span><div class="v">₹${fin(u.m)} cr</div></div><div><span class="lbl">QTD</span><div class="v ${cl(u.q)}">${sgn(u.q, 1, '%')}</div></div><div class="xs"><span class="lbl">Promoter</span><div class="v">${u.pr.toFixed(2)}%</div></div><div class="xs xl"><span class="lbl">FII</span><div class="v">${(u.fi || 0).toFixed(2)}%</div></div><div class="xs xl"><span class="lbl">DII</span><div class="v">${(u.di || 0).toFixed(2)}%</div></div>
    <span class="go">${ar ? 'Open dashboard' : 'Quick view'} ${arrow}</span></${ar ? 'a' : 'button'}>`;
  }).join('');
  return `<div class="uhead" style="--i:0"><div><span class="mono" style="font-size:11px;color:var(--acc);letter-spacing:.06em">STOCK UNIVERSE</span><h1>101 companies, every holder mapped</h1><span style="font-size:13px;color:var(--ink2);max-width:70ch;display:block">NSE 100 plus coverage adds. Holders come from Bloomberg OWN and are reconciled to SEBI filings. Market cap is the latest close × total shares in the latest filing.</span></div>
  <div class="ustat"><div><b>${cu(101)}</b><span class="lbl">Companies</span></div><div><b>${cu(D.univ.reduce((a, u) => a + u.h, 0))}</b><span class="lbl">Holder rows</span></div><div><b>${cu(D.univ.filter(u => u.ok).length)}</b><span class="lbl">All gates passed</span></div></div></div>
  <div style="--i:1;display:flex;flex-direction:column;gap:12px;margin-top:20px">${pinHtml || `<p class="cap">Your watchlist is empty. Open a company and tap Watch to pin it here.</p>`}</div>
  <section class="card" style="--i:2;margin-top:20px">
    <div class="frow"><div class="fchips" role="group" aria-label="Market cap filter">${[['all', 'All', D.univ.length], ['mega', '≥ ₹5 lakh cr', cnt.mega], ['large', '₹1–5 lakh cr', cnt.large], ['mid', '< ₹1 lakh cr', cnt.mid], ['watch', '★ Watchlist', S.watch.length]].map(o => `<button type="button" class="fchip" data-set="uB" data-val="${o[0]}" aria-pressed="${S.uB === o[0]}">${o[1]}<span class="ct">${o[2]}</span></button>`).join('')}</div>
    <div style="display:flex;gap:8px;align-items:center;flex:1;justify-content:flex-end;min-width:200px"><label for="uq" class="vh">Filter companies</label><input id="uq" class="field" type="search" placeholder="Filter by name or symbol" value="${esc(S.uQ)}" style="flex:1;max-width:280px;min-width:0">
    <label for="uSortSel" class="vh">Sort</label><select id="uSortSel" class="field pm2" data-sortsel="u">${[['m', 'Market cap'], ['q', 'QTD'], ['pr', 'Promoter %'], ['fi', 'FII %'], ['di', 'DII %'], ['n', 'Name']].map(o => `<option value="${o[0]}" ${S.uSort === o[0] ? 'selected' : ''}>${o[1]}</option>`).join('')}</select></div></div>
    <div id="uBody">${uBody()}</div>
  </section>${footer('holdermap database (101 runs, 23–24 Sep 2026) · NSE shareholding XBRL, latest filing per company · NSE bhavcopy close of ' + dfmt(NOW.d) + ', refreshed every trading day. QTD is from the ' + dfmt(LP ? LP.qbase : '2026-06-30') + ' close. Promoter 0.00 = no promoter group, as at HDFC Bank, ICICI Bank, ITC and L&amp;T.')}`;
}
function uBody() {
  const L = uList(), shown = L.slice(0, S.uN);
  const sb = (k, lab, cls) => `<span class="${cls || ''}"><button type="button" data-sort="u" data-k="${k}" ${S.uSort === k ? `aria-sort="${S.uDir > 0 ? 'ascending' : 'descending'}"` : ''}>${lab}${S.uSort === k ? (S.uDir > 0 ? ' ↑' : ' ↓') : ''}</button></span>`;
  let h = `<div><div class="lhead gU"><span class="l">#</span>${sb('n', 'Company', 'l')}${sb('m', 'Mkt cap ₹ cr')}${sb('p', 'Price ₹', 'xm')}${sb('q', 'QTD')}${sb('pr', 'Promoter %')}${sb('fi', 'FII %')}${sb('di', 'DII %')}${sb('h', 'Holders', 'xm')}${sb('ok', 'Gates')}<span></span></div>`;
  if (!shown.length) h += `<p class="cap" style="padding:20px 8px">No companies match. Clear the filter or pick another market-cap band.</p>`;
  shown.forEach((u, i) => {
    const rank = D.univ.indexOf(u) + 1, ar = u.s === 'ANANDRATHI';
    h += `<div class="lrow" style="--i:${Math.min(i, 20)}"><button type="button" class="rb gU" data-act="sheet" data-sym="${u.s}"><span class="rk">${rank}</span><span class="l" style="min-width:0"><span class="nm">${esc(u.n)}${ar ? ' <span class="pill" style="color:var(--acc);margin-left:6px;font-size:10px">DASHBOARD</span>' : ''}</span><span class="sb mono">${u.s}${S.watch.includes(u.s) ? ' ★' : ''}</span></span>
    <span class="xp" style="font-weight:600">${fin(u.m)}</span><span class="xp xm">${fin(u.p, 2)}</span><span class="xp ${cl(u.q)}">${sgn(u.q, 1, '%')}</span><span class="xp">${u.pr.toFixed(2)}<span class="minibar" style="width:${(u.pr * .6).toFixed(0)}px"></span></span><span class="xp">${u.fi == null ? '—' : u.fi.toFixed(2)}</span><span class="xp">${u.di == null ? '—' : u.di.toFixed(2)}</span><span class="xp xm mut">${u.h}</span><span class="xp"><span class="pill ${u.ok ? 'ok' : 'warn'}">${u.ok ? '7/7' : 'REVIEW'}</span></span>
    <span class="pm2" style="display:flex;flex-direction:column;align-items:flex-end"><b style="font-weight:600">₹${fin(u.m)} cr</b><span class="${cl(u.q)}" style="font-size:11px">${sgn(u.q, 1, '%')} QTD</span></span>
    <svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true" style="transform:rotate(-90deg)"><path d="M6 9l6 6 6-6"></path></svg></button></div>`;
  });
  h += '</div>';
  h += `<div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;font-size:12px;color:var(--ink3)"><span>Showing ${shown.length} of ${L.length}</span>${L.length > shown.length ? `<button type="button" class="more" data-act="more">Show ${Math.min(20, L.length - shown.length)} more</button>` : ''}<span>Tap a company for a quick view</span></div>`;
  return h;
}
function openSheet(sym) {
  const u = D.univ.find(x => x.s === sym); if (!u) return;
  const ar = u.s === 'ANANDRATHI', w = S.watch.includes(u.s), pub = Math.max(0, 100 - u.pr - (u.fi || 0) - (u.di || 0));
  const bar = [['Promoter', u.pr, 'var(--prom)'], ['FII', u.fi || 0, 'var(--fii)'], ['DII', u.di || 0, 'var(--dii)'], ['Public & others', pub, 'var(--oth)']];
  $('#sheetRoot').innerHTML = `<div class="scrim" data-act="close"></div><div class="sheet" role="dialog" aria-modal="true" aria-labelledby="shT"><div class="sbody">
   <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start"><div><span class="mono" style="font-size:11px;color:var(--ink3)">${u.s} · rank ${D.univ.indexOf(u) + 1} by mcap</span><h2 id="shT">${esc(u.n)}</h2></div><button type="button" class="x" data-act="close" aria-label="Close"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"></path></svg></button></div>
   <div style="display:flex;align-items:baseline;gap:12px"><span class="num" style="font-size:28px;font-weight:600">₹${fin(u.p, 2)}</span><span class="num ${cl(u.q)}" style="font-weight:600">${sgn(u.q, 1, '%')} QTD</span></div>
   <div><span class="lbl">Shareholding · ${u.f || 'latest'} filing</span><div class="pbar" style="margin-top:8px">${bar.map((b, i) => `<i style="width:${b[1].toFixed(2)}%;background:${b[2]};animation-delay:${i * 80}ms" data-tip="<b>${b[0]}</b><br>${b[1].toFixed(2)}%"></i>`).join('')}</div><div class="legend" style="margin-top:8px">${bar.map(b => `<span><span class="sw" style="background:${b[2]}"></span>${b[0]} ${b[1].toFixed(2)}%</span>`).join('')}</div></div>
   <div class="sgrid"><div><span class="lbl">Market cap</span><b>₹${fin(u.m)} cr</b></div><div><span class="lbl">Shareholders</span><b>${fin(u.sh)}</b></div><div><span class="lbl">Holders mapped</span><b>${u.h}</b></div><div><span class="lbl">Flagged</span><b>${u.fl}</b></div><div><span class="lbl">Gates</span><b class="${u.ok ? 'up' : 'dn'}">${u.ok ? 'All passed' : 'Needs review'}</b></div><div><span class="lbl">Last filing</span><b class="mono" style="font-size:14px">${u.f || '—'}</b></div></div>
   <div style="display:flex;gap:10px;flex-wrap:wrap"><button type="button" class="star" data-act="watch" data-sym="${u.s}" aria-pressed="${w}" style="min-height:40px"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"></path></svg><span>${w ? 'Watching' : 'Add to watchlist'}</span></button>${ar ? `<a class="btn pri" href="#overview" data-act="close" style="display:inline-flex;align-items:center;gap:8px;min-height:40px">Open full dashboard ${arrow}</a>` : ''}</div>
   ${ar ? '' : `<p class="note grey">The full dashboard is built for Anand Rathi Wealth in this version. holdermap already has this company's run (${u.h} holders), so it can be wired in the same way.</p>`}
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
    let s = svgOpen(w, h, 'Share price, quarter-end closes') + `<polygon points="3,${h} ${p} ${pts[pts.length - 1][0].toFixed(1)},${h}" fill="var(--surface2)"></polygon><polyline class="draw" pathLength="1" points="${p}" fill="none" stroke="var(--ink)" stroke-width="1.6" stroke-linejoin="round"></polyline>`;
    const step = Math.max(1, Math.floor(pts.length / 60));
    pts.forEach((q, i) => { if (i % step && i !== pts.length - 1) return; s += `<rect x="${(q[0] - (w / pts.length) * step / 2).toFixed(1)}" y="0" width="${((w / pts.length) * step).toFixed(1)}" height="${h}" fill="transparent" data-tip="<b>${dfmt(ser[i][0])}</b><br>Close ₹${fin(vals[i], 2)}"></rect>`; });
    s += `<circle cx="${pts[pts.length - 1][0].toFixed(1)}" cy="${pts[pts.length - 1][1].toFixed(1)}" r="3" fill="var(--acc)"></circle>`;
    el.innerHTML = s + '</svg>';
  },
  own(el, w) {
    const H = 230, top = 16, base = H - 26, left = 42, u = S.unit === 'val' ? 'val' : 'pct';
    const mx = u === 'val' ? 35000 : 100, ticks = u === 'val' ? [0, 10000, 20000, 30000] : [0, 25, 50, 75, 100], sc = (base - top) / mx;
    const cw = (w - left) / 6, bw = Math.min(78, cw * .62);
    let s = svgOpen(w, H, 'Ownership by category, Mar-25 to Jun-26');
    ticks.forEach(t => { const y = base - t * sc; s += `<line class="grid" x1="${left}" x2="${w}" y1="${y.toFixed(1)}" y2="${y.toFixed(1)}"></line><text x="${left - 8}" y="${(y + 4).toFixed(1)}" text-anchor="end">${u === 'val' ? fin(t) : t + '%'}</text>`; });
    T.forEach((t, i) => {
      const x = left + i * cw + (cw - bw) / 2; let y = base;
      let g = `<g class="bar" style="--i:${i}">`;
      CATS.forEach(c => { const v = tv(t, c.k, u), hh = v * sc; y -= hh; g += `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(0, hh).toFixed(1)}" fill="${CC[c.k]}" data-tip="<b>${c.l} · ${t.q}</b><br>${(100 * t[c.k] / t.tot).toFixed(2)}% · ₹${fin(t[c.k] * t.px / 1e7)} cr"></rect>`; if (u !== 'val' && c.k === 'prom' && bw > 30) g += `<text class="inv" x="${(x + bw / 2).toFixed(1)}" y="${(y + hh / 2 + 4).toFixed(1)}" text-anchor="middle" style="pointer-events:none">${v.toFixed(1)}</text>`; });
      if (u === 'val') g += `<text class="strong" x="${(x + bw / 2).toFixed(1)}" y="${(y - 6).toFixed(1)}" text-anchor="middle">${fin(t.tot * t.px / 1e7)}</text>`;
      s += g + `</g><text class="lab" x="${(x + bw / 2).toFixed(1)}" y="${H - 8}" text-anchor="middle">${t.q}</text>`;
    });
    el.innerHTML = s + '</svg>';
  },
  mcap(el, w) {
    const MC = T.map(t => Math.round(t.tot * t.px / 1e7)).concat([Math.round(MCAP)]), LB = T.map(t => t.q).concat(['Now']);
    const H = 170, top = 18, base = H - 22, mx = Math.ceil(Math.max.apply(null, MC) * 1.12 / 5000) * 5000, sc = (base - top) / mx, cw = w / 7, bw = Math.min(46, cw * .66);
    let s = svgOpen(w, H, 'Market cap at quarter-end');
    s += `<line class="grid" x1="0" x2="${w}" y1="${base}" y2="${base}"></line>`;
    MC.forEach((v, i) => { const x = i * cw + (cw - bw) / 2, hh = v * sc; s += `<g class="bar" style="--i:${i}"><rect x="${x.toFixed(1)}" y="${(base - hh).toFixed(1)}" width="${bw.toFixed(1)}" height="${hh.toFixed(1)}" fill="${i === 6 ? 'var(--ink)' : 'var(--grey)'}" data-tip="<b>${LB[i]}</b><br>₹${fin(v)} cr"></rect></g><text class="${i === 6 ? 'strong' : 'lab'}" x="${(x + bw / 2).toFixed(1)}" y="${(base - hh - 5).toFixed(1)}" text-anchor="middle" style="font-size:10px">${w < 420 ? (v / 1000).toFixed(1) + 'k' : fin(v)}</text><text x="${(x + bw / 2).toFixed(1)}" y="${H - 6}" text-anchor="middle" style="font-size:10px">${LB[i]}</text>`; });
    el.innerHTML = s + '</svg>';
  },
  earn(el, w) {
    const H = 210, top = 20, base = H - 26, left = 36, m = S.eMetric, cw = (w - left) / 6;
    let s = svgOpen(w, H, 'Earnings by quarter');
    const series = m === 'pat' ? null : m === 'eps' ? EPS : PAT.map((p, i) => 100 * p / REV[i]);
    const mx = m === 'pat' ? 350 : m === 'eps' ? 12 : 60, ticks = m === 'pat' ? [0, 100, 200, 300] : m === 'eps' ? [0, 4, 8, 12] : [0, 20, 40, 60], sc = (base - top) / mx;
    ticks.forEach(t => { const y = base - t * sc; s += `<line class="grid" x1="${left}" x2="${w}" y1="${y.toFixed(1)}" y2="${y.toFixed(1)}"></line><text x="${left - 6}" y="${(y + 4).toFixed(1)}" text-anchor="end">${t}${m === 'mgn' ? '%' : ''}</text>`; });
    for (let i = 0; i < 6; i++) {
      const cx = left + i * cw + cw / 2, bw = Math.min(32, cw * .32);
      if (m === 'pat') {
        s += `<g class="bar" style="--i:${i}"><rect x="${(cx - bw - 2).toFixed(1)}" y="${(base - REV[i] * sc).toFixed(1)}" width="${bw.toFixed(1)}" height="${(REV[i] * sc).toFixed(1)}" fill="var(--rev)" data-tip="<b>${EQ[i]} · ${EQd[i]}</b><br>Revenue ₹${fin(REV[i], 2)} cr"></rect></g><g class="bar" style="--i:${i + .5}"><rect x="${(cx + 2).toFixed(1)}" y="${(base - PAT[i] * sc).toFixed(1)}" width="${bw.toFixed(1)}" height="${(PAT[i] * sc).toFixed(1)}" fill="${i === 5 ? 'var(--acc)' : 'var(--ink)'}" data-tip="<b>${EQ[i]} · ${EQd[i]}</b><br>PAT ₹${fin(PAT[i], 2)} cr · margin ${(100 * PAT[i] / REV[i]).toFixed(1)}%<br>EPS ₹${EPS[i].toFixed(2)} (166.04 mn sh)"></rect></g><text class="strong" x="${(cx + 2 + bw / 2).toFixed(1)}" y="${(base - PAT[i] * sc - 6).toFixed(1)}" text-anchor="middle">${Math.round(PAT[i])}</text>`;
      } else {
        const v = series[i], bw2 = Math.min(44, cw * .5);
        s += `<g class="bar" style="--i:${i}"><rect x="${(cx - bw2 / 2).toFixed(1)}" y="${(base - v * sc).toFixed(1)}" width="${bw2.toFixed(1)}" height="${(v * sc).toFixed(1)}" fill="${i === 5 ? 'var(--acc)' : 'var(--ink)'}" data-tip="<b>${EQ[i]} · ${EQd[i]}</b><br>${m === 'eps' ? 'EPS ₹' + v.toFixed(2) + ' on 166.04 mn shares<br>Reported ₹' + EPSR[i].toFixed(2) : 'PAT margin ' + v.toFixed(1) + '%'}"></rect></g><text class="strong" x="${cx.toFixed(1)}" y="${(base - v * sc - 6).toFixed(1)}" text-anchor="middle">${m === 'eps' ? v.toFixed(2) : v.toFixed(1) + '%'}</text>`;
      }
      s += `<text class="lab" x="${cx.toFixed(1)}" y="${H - 8}" text-anchor="middle">${w < 460 ? EQd[i] : EQ[i]}</text>`;
    }
    el.innerHTML = s + '</svg>';
  }
};
function drawCharts(root, still) {
  $$('.chart[data-c]', root).forEach(el => {
    const f = CH[el.dataset.c]; if (!f) return;
    const w = Math.max(160, Math.floor(el.clientWidth));
    f(el, w);
    if (still) $$('.bar,.draw', el).forEach(n => { n.style.animation = 'none'; if (n.classList.contains('draw')) n.style.strokeDashoffset = 0; });
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
function parseHash() {
  const h = (location.hash || '').replace('#', '');
  if (ALIAS[h]) { S.route = ALIAS[h][0]; if (ALIAS[h][1]) S.hTab = ALIAS[h][1]; return; }
  if (h === 'watchlist') { S.route = 'universe'; S.uB = 'watch'; return; }
  S.route = ROUTES.includes(h) ? h : (h ? 'overview' : store.get('route', 'overview'));
}
function render() {
  const company = S.route !== 'universe';
  const prevLast = document.documentElement.dataset.route;
  $('#co').innerHTML = company ? companyHeader() : '';
  const main = $('#main');
  main.innerHTML = ({ universe: viewUniverse, overview: viewOverview, holders: viewHolders, flows: viewFlows, evidence: viewEvidence })[S.route]();
  main.classList.remove('view'); void main.offsetWidth; main.classList.add('view');
  document.documentElement.dataset.route = S.route;
  $$('.tnav a').forEach(a => { const on = (a.dataset.nav === 'universe' && S.route === 'universe' && S.uB !== 'watch') || (a.dataset.nav === 'watchlist' && S.route === 'universe' && S.uB === 'watch') || (a.dataset.nav === 'company' && company); on ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current'); });
  $$('.bnav a').forEach(a => a.dataset.b === S.route ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current'));
  document.title = company ? 'holdermap' : 'holdermap';
  requestAnimationFrame(() => { drawCharts(document); placeSegs(document); if (S.first || prevLast !== S.route) countUp(document); S.first = false; focusPending(); });
  store.set('route', S.route);
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
    if (row.dataset.flow) { const f = D.flows[S.fP].all.find(o => slug(o.n) === id); det.innerHTML = f ? flowDetail(f.n) : ''; }
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
    else if (k === 'em') { S.eMetric = v; patch('earnBody', earnBody); }
    else if (k === 'rh') { S.rH = v; patch('retBody', retBody); }
    else if (k === 'hTab') { S.hSort = 's'; S.hDir = -1; const c = $('#hCard'); if (c) { c.firstElementChild.outerHTML = holdersHead(); patch('hBody', holdersBody); if (t.classList.contains('kpi')) c.scrollIntoView({ behavior: RM ? 'auto' : 'smooth', block: 'start' }); } }
    else if (k === 'basis') patch('hBody', holdersBody);
    else if (k === 'fP') { S.fG = null; patch('fBody', flowsBody); }
    else if (k === 'uB') { S.uN = 20; $$('.fchip[data-set="uB"]').forEach(b => b.setAttribute('aria-pressed', b.dataset.val === v)); patch('uBody', uBody); }
    $$(`[data-set="${k}"]`).forEach(b => b.setAttribute('aria-pressed', b.dataset.val === S[k]));
    requestAnimationFrame(() => placeSegs(document));
    return;
  }
  if (t.dataset.sort) {
    const w = t.dataset.sort, k = t.dataset.k;
    if (w === 'h') { if (S.hSort === k) S.hDir *= -1; else { S.hSort = k; S.hDir = k === 'n' || k === 'cty' ? 1 : -1; } patch('hBody', holdersBody); }
    else { if (S.uSort === k) S.uDir *= -1; else { S.uSort = k; S.uDir = k === 'n' ? 1 : -1; } patch('uBody', uBody); }
    return;
  }
  if (t.dataset.go) {
    e.preventDefault();
    const p = t.dataset.go.split('|');
    if (p[0] === 'flows') { S.fP = p[1]; S.fG = null; S.focus = p[2]; go('flows'); }
    else if (p[0] === 'holders') { S.hTab = p[1]; S.focus = p[2] || null; S.hSort = 's'; S.hDir = -1; S.basis = 'pct'; go('holders'); }
    else if (p[0] === 'cat') { S.openCat[p[1]] = true; patch('ownBody', ownBody); setTimeout(() => $('#own').scrollIntoView({ behavior: RM ? 'auto' : 'smooth', block: 'start' }), 60); }
    return;
  }
  const a = t.dataset.act;
  if (a === 'cat') { S.openCat[t.dataset.k] = !S.openCat[t.dataset.k]; patch('ownBody', ownBody); }
  else if (a === 'catgo') { S.openCat[t.dataset.k] = true; patch('ownBody', ownBody); $('#own').scrollIntoView({ behavior: RM ? 'auto' : 'smooth', block: 'start' }); }
  else if (a === 'row' || a === 'frow') toggleRow(t.closest('.lrow'));
  else if (a === 'fgrp') { S.fG = S.fG === t.dataset.g ? null : t.dataset.g; patch('fBody', flowsBody); }
  else if (a === 'sheet') { if (t.dataset.sym === 'ANANDRATHI' && t.classList.contains('rb')) go('overview'); else openSheet(t.dataset.sym); }
  else if (a === 'close') { closeSheet(); }
  else if (a === 'more') { S.uN += 20; patch('uBody', uBody); }
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
  if (e.target.dataset.sortsel === 'u') { S.uSort = e.target.value; S.uDir = e.target.value === 'n' ? 1 : -1; patch('uBody', uBody); }
});
let uqT;
document.addEventListener('input', e => {
  if (e.target.id === 'uq') { clearTimeout(uqT); S.uQ = e.target.value; S.uN = 20; uqT = setTimeout(() => patch('uBody', uBody), 120); }
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
  gsItems = D.univ.filter(u => u.n.toLowerCase().includes(q) || u.s.toLowerCase().includes(q)).slice(0, 8); gsSel = 0;
  r.hidden = false; $('#q').setAttribute('aria-expanded', 'true');
  r.innerHTML = gsItems.length ? gsItems.map((u, i) => `<button type="button" role="option" data-gs="${u.s}" class="${i === 0 ? 'act' : ''}"><span><b style="font-weight:600">${esc(u.n)}</b><span class="mono" style="display:block;font-size:11px;color:var(--ink3)">${u.s}</span></span><span class="num" style="font-size:12px;color:var(--ink2)">₹${fin(u.m)} cr</span></button>`).join('') : `<div class="empty">No company matches “${esc(v)}”.</div>`;
}
function gsClose() { const r = $('#gsres'); r.hidden = true; r.innerHTML = ''; $('#q').setAttribute('aria-expanded', 'false'); }
function gsPick(sym) { gsClose(); $('#q').value = ''; $('#top').classList.remove('searching'); if (sym === 'ANANDRATHI') go('overview'); else openSheet(sym); }
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
