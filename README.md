# holdermap dashboard

A shareholding and ownership dashboard for **Anand Rathi Wealth Ltd** (NSE: ANANDRATHI). It also has a universe screen covering the 101 companies that holdermap maps. It is a static web app that works on phones and laptops.

## Screens

| Screen | What it shows |
|---|---|
| Universe | 101 companies with a market-cap filter, search, sorting, a watchlist and a quick view for each company |
| Overview | Ownership trend for Promoter, FII, DII, Individuals and Others over six filed quarters, in % / ₹ crore / shares, with breakdowns you can expand. Also valuation, earnings and price returns against the Nifty 50 and Nifty 500 |
| Shareholding | Top 20 FIIs, top 20 DIIs and individual holders. Each shows shares, value, % of total, % of free float, a 6-quarter trend and mean, max and min, and expands into quarter-by-quarter detail |
| Buyers & sellers | Top 25 buyers and sellers (the filed quarter or the current quarter so far), with net flow by holder type |
| Evidence & gates | Reconciliation gates, provenance tiers, category sums, quarter-end prices and the analyst review queue |

## Data sources

| Data | Source |
|---|---|
| Shareholding | NSE shareholding pattern XBRL (SEBI LODR Reg. 31), Mar-25 to Jun-26: `pipeline/inputs/xbrl/` |
| Holders, categories, gates | holdermap run of 23 Sep 2026 on the Bloomberg OWN export: `pipeline/inputs/run.json` |
| Stock prices | NSE bhavcopy daily closes. 10 Aug – 22 Sep 2026 comes from stockanalysis.com, which matched 5 NSE closes exactly. Bonus-adjusted for the 1:1 bonuses of 5 Mar 2025 and 3 Jun 2026 |
| Results | Company press releases and investor presentations: PAT and revenue as reported. EPS is shown as reported and also restated to 166,041,268 shares |
| Nifty 50 | Closes from Business Standard market wraps and Yahoo Finance |
| Nifty 500 | Closes from investing.com, plus anandrathi.com's 1Y and 3Y returns. Nifty 500 closes before Aug 2026 were not verified, so those return cells show n/a until `scripts/refresh_dashboard_prices.py` fills them from yfinance |

Hover or tap any return figure to see its inputs.

## Build

```bash
python3 pipeline/export.py   # rebuild src/data.json from pipeline/inputs (optional)
python3 build.py             # writes dashboard/site/ and dashboard/standalone.html
```

`dashboard/standalone.html` is a single file you can open directly. `dashboard/site/` is the multi-file version for hosting under a strict CSP (no inline scripts).

## Deploy to AWS (S3 + CloudFront, access-link gated)

```bash
pip install yfinance          # optional: fills the missing Nifty 500 closes
scripts/deploy_dashboard.sh   # the first run creates the stack (~5 min) and prints https://<id>.cloudfront.net/?key=<random>
scripts/deploy_dashboard.sh --rotate   # issue a new key; old links stop working
```

The access key is kept only in `data/dashboard/access_key` (gitignored). The CloudFront function stores only its SHA-256. The bucket is private (OAC), and the site is served over HTTPS with `noindex`.

## Layout

```
src/            head.html (CSS), body.html, app.js, data.json
dashboard/      site/ (deployable), standalone.html
pipeline/       data.py, export.py, prices.py, common.py, inputs/
infra/          dashboard.yaml (CloudFormation)
scripts/        deploy_dashboard.sh, refresh_dashboard_prices.py
```
