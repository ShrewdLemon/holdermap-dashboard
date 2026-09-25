# holdermap dashboard

Shareholding and ownership dashboards for **2,476 NSE-traded companies**. Each company has its own page with the ownership trend, named holders, buyers and sellers, earnings, valuation and returns. It is a static web app that works on phones and laptops. It is private and served from AWS behind an access link. The key is not in this repo.

Every number comes from an official filing or exchange file: SEBI shareholding patterns, NSE and BSE daily prices, and quarterly results filed with the exchanges. Nothing is typed in by hand. Checks against NSE's and BSE's own published figures run before every data release (see [Accuracy](#accuracy)).

## Coverage (25 Sep 2026)

| Group | Pages | Holder names from |
|---|---|---|
| Nifty 500 (current members) | 500 | Bloomberg Security Ownership export for the NSE 100 and ANANDRATHI (101 companies). SEBI filings plus fund disclosures for the other 399 |
| Joining the Nifty 500 on 30 Sep 2026 | 24 | SEBI filings plus fund disclosures |
| Other main-board companies | 1,951 | SEBI filings plus fund disclosures. 242 of them file with BSE, and their filings come from BSE |
| NSE (the exchange company, BSE-only) | 1 | A listing snapshot from its prospectus until its first quarterly filing |

"SEBI filings plus fund disclosures" means three sources:
- **SEBI shareholding filings:** holders of 1% or more.
- **Mutual-fund portfolio disclosures:** every fund house, named at fund-house level.
- **SEC N-PORT filings:** US-registered funds.

The 26 companies leaving the Nifty 500 on 30 Sep keep their pages and are tagged. The universe table has filters for Nifty 500, joining, leaving and outside the Nifty 500.

**Not built yet:**
- **Main board, 110 companies:**
  - 35 listed in Aug–Sep 2026 and have no quarter-end filing yet.
  - About 52 moved from the SME board, so their history is under NSE's SME index.
  - 7 are suspended and no longer file.
  - About 16 have data problems.
- **SME board:** 572 companies (next phase).
- **REITs joining the Nifty 500:** 3 (EMBASSY, BIRET, BAGMANE). They file unitholding patterns in a different format.

## Screens

| Screen | What it shows |
|---|---|
| Universe | Every company with search, market-cap and index filters, sorting, a watchlist and a quick view |
| Overview | Ownership trend over six filed quarters (Promoter, FII, DII, Individuals, Others, plus ADR/GDR shares where a company has them) in % / ₹ crore / shares. Also pattern and what changed, valuation, earnings, and returns against the Nifty 50 and Nifty 500 |
| Shareholding | Top foreign and domestic holders and individuals. Each shows shares, value, % of total, % of free float and a quarterly trend, and expands to quarter-by-quarter detail |
| Buyers & sellers | Top buyers and sellers between the last two filings (and quarter to date where the data allows), with net flow by holder type |
| Evidence & gates | The eight holder checks, how each holder was categorised, category sums against the filing, quarter-end prices and a review queue |

## Data sources

| Data | Source | Refreshed |
|---|---|---|
| Shareholding by category | SEBI shareholding pattern XBRL (LODR Reg. 31) from NSE, or from BSE for companies that file there | Each quarter (company export) |
| Named holders | holdermap runs: Bloomberg OWN (101 companies) or filings + mutual-fund disclosures + SEC N-PORT | Each quarter |
| Daily prices | NSE daily bhavcopy (BSE's daily file for BSE-only companies), adjusted for bonuses, splits and demergers | Every weekday evening, automatically |
| Nifty 50 / Nifty 500 | NSE's daily index files, plus the full history from niftyindices.com (Nifty 50 from Jul 1990, Nifty 500 from Jan 1995) | Every weekday evening |
| Quarterly results | Results filed with NSE (integrated-filing iXBRL, older XBRL). Three BSE-only companies use their own published results statements | Each results season |
| Book value, ROE, dividends | Half-yearly balance sheets in the same filings; NSE corporate actions for dividends | Each results season |
| Corporate actions | NSE corporate actions and daily PR files; ex-dates checked against the actual price move | Each export; new ones detected daily from NSE's adjusted previous close |

## Accuracy

These checks run on every data release. The results as of 25 Sep 2026 are in brackets.

- **Shareholding %:** each company's latest promoter, FII and DII percentages are compared with NSE's published figure and BSE's copy of the filing (`scripts/validate_universe.py`). [2,443 of 2,444 comparable companies within 0.05 pp. The exception matches NSE exactly; BSE's copy differs.]
- **Market cap:** NSE's issue size × close, compared with NSE's own market-cap file. [2,476 within 0.01%.]
- **Earnings:** EPS × shares must equal PAT attributable to owners within 5%. Misses are flagged on the page, not hidden.
- **Holder lists:** eight checks against the filings: counts reconcile, promoter coverage, category sums, only the twelve categories, blank/zero pattern, every row evidenced, price provenance, and fund holdings within the filing's mutual-fund total. [94.6% of new main-board companies pass all eight; failures are shown on each page.]
- **Pages:** a browser sweep opens every company on every tab with every toggle and looks for script errors or NaN/undefined. [9,904 views, 0 problems.]

## Conventions (how numbers are defined)

- **Percentages are on SEBI's basis:** shares ÷ (total − shares underlying ADRs/GDRs). Depository-receipt shares get their own line in every quarter, so companies that moved them inside "foreign institutions" in the new filing format (e.g. ICICI Bank, Jun-26) still compare quarter to quarter. A note shows the as-filed figure.
- **FII as filed:** strategic foreign stakes (foreign direct investment, e.g. BAT in ITC) stay inside FII as SEBI reports them, and are shown as their own sub-line.
- **Market cap** uses NSE's current share count (issue size), not the last filing's, because mergers and QIPs change it between filings.
- **EPS:** P/E uses TTM PAT attributable to owners. EPS is shown as reported, plus a row restated for splits and bonuses where needed.
- **Returns** are price returns to the latest close. "Since listing" compares with the Nifty 50 and Nifty 500 from the same date. Where the old price history has an unexplained break, the long-run return starts from the first date after it, and is labelled that way.
- **Prices** are end-of-day. The quarter-to-date base is the close on the last day of the previous quarter.

## How it is built and deployed

```
local (needs ~/Projects data)                      CI (AWS CodeBuild, on push + 18:45/21:30 IST weekdays)
holdermap runs ──► pipeline/company.py ──► src/co/<SYM>.json, src/univ.json ──► git ──► pipeline/live.py (latest prices)
NSE filings    ──► pipeline/results.py ──► pipeline/inputs/results/<SYM>.json          build.py (dashboard/site)
                                                                                         scripts/deploy.sh (S3 + CloudFront)
```

- `src/` is the app (`app.js`, `head.html` for CSS, `body.html`) plus the committed data: one JSON per company in `src/co/` and the universe in `src/univ.json`.
- `pipeline/live.py` fetches the latest NSE (and BSE) closes and writes `dashboard/prices_full.json`. `build.py` puts each company's price block into that company's file and writes a small shared `prices.js`.
- A push to `main` builds and publishes in about 2 minutes. Builds can overlap; `scripts/deploy.sh` only publishes a commit at least as new as the live one.

See [docs/PIPELINE.md](docs/PIPELINE.md) for the quarterly data refresh, adding companies, and the known traps.

## Working on the UI

Edit `src/` only. `dashboard/` is build output and is not committed.

```bash
python3 pipeline/live.py --offline   # prices from the local cache (drop --offline to fetch the latest)
python3 build.py                     # assemble dashboard/site/
python3 -m http.server 8765 --directory dashboard/site   # open http://localhost:8765
```

Rules:
- **No typed prices or dates:** never type a price, date or company fact into `src/app.js`. Read it from the company data (`D`, `CO`) and the live price layer (`NOW`, `OQ`).
- **Test every data shape:** every page must work for companies with one filed quarter, no promoter group, loss quarters, missing quarter-end prices and BSE-only listings. Check a few of each (e.g. `VAML`, `HDFCBANK`, `TATACHEM`, `ACGL`, `NSE`).

## Infrastructure

| Piece | What | Command |
|---|---|---|
| Site | CloudFormation stack `holdermap-dashboard` (`infra/dashboard.yaml`): private S3 bucket, CloudFront, access-link gate (CloudFront function holding only the key's SHA-256) | `scripts/deploy_infra.sh` (`--rotate` issues a new key; old links stop working) |
| Auto-deploy | Stack `holdermap-dashboard-pipeline` (`infra/pipeline.yaml`): CodeBuild project on push to `main` via an AWS CodeConnections GitHub connection, plus evening refreshes | `scripts/deploy_pipeline.sh <connection-arn>` |
| Everyday publish | Latest prices, build, upload, invalidate | `scripts/deploy.sh` (CI runs it) |

The access key and link live only in `.local/` (gitignored). The price cache is kept between builds in the site bucket under `_state/`.

## Layout

```
src/                 app.js, head.html (CSS), body.html; co/<SYM>.json (one per company), univ.json, univ_extra.json
pipeline/            company.py (company export), results.py (+ nseresults/), live.py (daily prices), index_hist.py,
                     extra_nse.py (NSE listing snapshot), inputs/ (index lists, results, price universe, Nifty history)
scripts/             deploy.sh, deploy_infra.sh, deploy_pipeline.sh, validate_universe.py
infra/               dashboard.yaml (site), pipeline.yaml (CodeBuild + schedules)
tests/               test_live.py (runs in CI), test_company.py (ANANDRATHI regression; needs local data, skipped in CI)
docs/PIPELINE.md     data refresh runbook and traps
```

Legacy: `pipeline/export.py`, `data.py`, `prices.py`, `common.py` and `src/data.json` are the original single-company (ANANDRATHI) builder, kept as the reference that `tests/test_company.py` checks `pipeline/company.py` against.
