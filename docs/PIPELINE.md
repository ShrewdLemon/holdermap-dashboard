# Data pipeline runbook

How the company data in `src/co/` is produced and refreshed, and the traps found while building it. The site itself redeploys automatically (see the README). This file is about the **holdings data**, which is rebuilt locally each quarter.

## What runs where

| Step | Where | Output | Speed |
|---|---|---|---|
| Daily prices, Nifty closes, corporate actions found from NSE's adjusted previous close | CI, every push and 18:45 / 21:30 IST weekdays (`pipeline/live.py`) | `dashboard/prices_full.json`, then each company file and `prices.js` | ~5 s for 2,476 companies |
| Holder tables (holdermap runs) | Local | `~/Projects/nse100-holders/companies/<SYM>/run.json` (Bloomberg, NSE 100); `~/Projects/nse500-runs/<SYM>/run.json` (filing mode) | ~0.5 s per company with 6 workers, after preparation |
| Quarterly results | Local (`pipeline/results.py`) | `pipeline/inputs/results/<SYM>.json` | ~1.3 s per company: NSE's API allows 1 request per second |
| Company export | Local (`pipeline/company.py`) | `src/co/<SYM>.json`, `src/univ.json`, `pipeline/inputs/px_universe.json` | ~7 s per 30 companies |
| Checks | Local (`scripts/validate_universe.py`, tests, browser sweep) | Report | ~1 min |

The local steps need the market data already on this machine:

| Path | What |
|---|---|
| `~/Projects/msci/data_dump/` | NSE daily prices since 1994 (`bhavcopy.db`), corporate actions, NSE shareholding XBRL and indexes, BSE shareholding JSON (`bse_shp_all`, `bse_shp_hist`) |
| `~/Projects/exports/freefloat/data/` | Every NSE shareholding XBRL since Sep-2021 (`xbrl_raw/`, index in `shp/`), BSE XBRL for BSE filers (`bse/xbrl/`, `bse/scripmap.json`), daily PR files |
| `~/Projects/holdermap/` | The holdermap engine and its caches (fund disclosures, SEC N-PORT, registries) |
| `~/Projects/nse500-runs/` | The batch driver `batch.py`, its work lists (`todo*.json`), `STATUS.json`, and the holdermap fixes patch (`holdermap-fixes.patch`) |

## Quarterly refresh (after each quarter's filings)

Shareholding patterns are due within 21 days of quarter end, and results within 45 days (60 for Q4).

1. **Holdermap code with the batch fixes.** The six fixes found on 25 Sep 2026 live in `~/Projects/nse500-runs/holdermap-fixes.patch`. Until they are merged into holdermap, use a worktree with the patch applied and point every command at it with `HOLDERMAP_ROOT=<worktree>`. Without it, runs silently use the unpatched checkout. `run.json` records which code ran in `batch.holdermap`.
2. **Holder runs** (from `~/Projects/holdermap`, with `todo.json` holding the companies to do):
   ```bash
   export HOLDERMAP_ROOT=<patched worktree> HM_FETCH_FROM=<first quarter shown, e.g. 2025-06-30>
   .venv/bin/python ~/Projects/nse500-runs/batch.py prepare --workers 8   # filings + one pass over the SEC N-PORT files
   .venv/bin/python ~/Projects/nse500-runs/batch.py run --workers 6       # add --force to rerun existing runs
   .venv/bin/python ~/Projects/nse500-runs/batch.py bse-import SYM ...     # companies that file with BSE ("permitted")
   ```
   The NSE 100 use the team's Bloomberg exports instead (holdermap `nse100.py`, into `~/Projects/nse100-holders`).
   **Bloomberg exports for other companies** (one OWN screen per sheet, 2025 Q2 – 2026 Q3, grouped by investment manager):
   ```bash
   .venv/bin/python ~/Projects/nse500-runs/batch.py bbg-plan ~/Projects/nse500-runs/bloomberg/<date>-team   # -> todo.bbg.json, bbg_skipped.json
   BATCH_TODO=~/Projects/nse500-runs/todo.bbg.json .venv/bin/python ~/Projects/nse500-runs/batch.py run --workers 8 --force
   ```
   `bbg-plan` maps each sheet to a symbol by the ISIN on the screen (NSE's equity list catches ISINs changed by splits) and lists the sheets it leaves out, with the reason. Send those back to the team. The run a Bloomberg run replaces is kept as `run.filing.json`. 532 companies took 12 minutes on 8 workers. Pages show "Bloomberg, <date>" from the workbook's saved date.
3. **Results:** `python3 pipeline/results.py --syms SYM1,SYM2,...`. Rerun anything logged as `HTTP 0` or `no NSE list`.
4. **Export:** `python3 pipeline/company.py --nse100 --nifty500` for the index companies, and `python3 pipeline/company.py --add SYM ...` for the rest. For everything at once, run four processes with `--no-univ` on disjoint symbol lists, then `python3 pipeline/company.py --univ-only`: all 2,475 in about 100 s.
5. **Move the quarter window forward:**
   - The filed quarters in `pipeline/company.py`.
   - `OPEN_Q_END` in `pipeline/live.py` (e.g. `2026-12-31`).
   - The Nifty 500 list (`pipeline/inputs/ind_nifty500list.csv`) after each semi-annual rebalance, and the scheduled changes (`--nifty500` reads `~/Projects/netra/data/nifty_index_changes.csv`).
6. **Check:**
   - `python3 scripts/validate_universe.py`: every mismatch needs a reason before release.
   - `python3 -m unittest discover -s tests`.
   - A browser sweep of every company, tab and toggle.
7. **Commit and push.** CI publishes. Large pushes need `git config http.postBuffer 524288000`.

## Adding companies

- **Any NSE-listed company:** it needs a holder run, then `pipeline/company.py --add SYM`. Companies that file with BSE need `batch.py bse-import SYM` first, which uses the local BSE copies.
- **Companies outside NSE** (e.g. NSE itself, BSE-only): write an `extra_*.py` like `pipeline/extra_nse.py`. It produces a snapshot page (`"snapshot": true`), a universe row in `src/univ_extra.json`, and a price feed entry in `pipeline/inputs/px_extra.json` (`"exch": "BSE"`, matched by ISIN in BSE's daily file).

## Traps (each one cost time)

- **NSE's API** (www.nseindia.com) is Akamai-protected: one request per second, stop at the first refusal, and check the body, not just the status. A block can last days. The archive host (nsearchives) never blocks.
- **SME companies** need `index=sme` in NSE's API; `index=equities` returns an empty list. This also affects companies that moved from SME to the main board: their early quarters are under the SME index.
- **"Permitted" companies:** 284 main-board names trade on NSE but file with BSE. NSE's API returns an empty list for them. BSE's API (api.bseindia.com) was returning 403 on 25 Sep 2026, so use the local BSE copies.
- **Depository receipts:** SEBI's percentages exclude shares underlying ADRs/GDRs (C1). From Jun-2026 some filings put them inside foreign institutions instead. `trend[].dr`, `den`, `dr_in_public` and `filed` handle both.
- **BSE's stored copy is the company's latest filing.** After a special filing (merger, QIP) it is not the quarter-end one; `validate_universe.py` skips it then.
- **Price series:** a move over 25% in a day is only accepted when NSE's own previous close agrees (a real move). Otherwise it is a corporate action: re-base with NSE's adjusted previous close, or fix the event in the export.
- **`batch.py prepare` without `HM_FETCH_FROM`** downloads every filing back to 2021, one by one, which is slow and unnecessary.
- **zsh does not split `$VAR`:** pass symbol lists as `${=S}`, or the whole list arrives as one symbol.
- **Bloomberg sheets:** check the screen, not the tab name. On 25 Sep, the "CBOI" tab held CEMPRO's screen and "Diligent Media" held Digicontent's. A ticker changed by a rename can show no ISIN and only the current quarter (HEG). Bloomberg adds "/India" to Indian names ("HDFC Trustee Co Ltd/India").
- **Duplicate holdings:** Bloomberg lists a fund house's trustee (from the filing) and its asset manager, and some holders under two names; holdermap adds filing-only rows that can repeat a Bloomberg row. `reconcile()` in `pipeline/company.py` lists each holding once. Check the log in `cache/company_report.json` after a new batch.
- **Bloomberg below the filing:** on 25 Sep, 103 of the 3,043 holders the filings list at 1% or more showed less, zero or nothing on the Bloomberg pages (LIC policy funds, NPS schemes, one FPI). `fill_from_filing()` puts the filed count back from the company's filing-mode run (`run.filing.json`, kept beside each Bloomberg run). A brand is matched only within the same category: LIC the insurer is not LIC Mutual Fund or LIC Pension Fund.
- **Long jobs:** keep the Mac awake and on power (`caffeinate -dimsu -t <seconds>`, check `pmset -g batt`). A sleep on battery paused one run for about 50 minutes and caused network failures that had to be retried.
