# Contributing

## UI changes (most changes)

1. Branch from `main` and edit only `src/`: `app.js` for behaviour, `head.html` for CSS, `body.html` for the page shell.
2. Preview locally:
   ```bash
   python3 pipeline/live.py --offline && python3 build.py
   python3 -m http.server 8765 --directory dashboard/site   # http://localhost:8765
   ```
3. Check that the pages still work for the unusual cases: `VAML` (one filed quarter), `HDFCBANK` (no promoter group), `TATACHEM` (loss quarters), `ICICIBANK` (ADR shares), `ACGL` (files with BSE), `NSE` (listing snapshot, BSE-only), `FIVESTAR` (a missing quarter).
4. Run `node --check src/app.js` and `python3 -m unittest discover -s tests`.
5. Open a pull request. Merging to `main` publishes within a few minutes: CodeBuild runs `buildspec.yml`, which does the JS syntax check, tests, fresh prices, build and upload.

## Rules

- Never type a price, date, count or company fact into `src/app.js`. Read it from the company data (`D`, `CO`), the latest prices (`NOW`, `OQ`) or the universe (`U`).
- Percentages use SEBI's basis (see the README's conventions). Don't recompute them on the full share count.
- Keep text neutral and specific: say what a number is and where it comes from, and show "n/a" or "—" with a reason rather than a guess.
- Do not commit `dashboard/` (build output), `cache/`, `.local/` (the access key) or `pipeline/inputs/*/raw/` (large source PDFs).

## Data changes

The company data (`src/co/`, `src/univ.json`, `pipeline/inputs/results/`) is produced by the local pipeline in [docs/PIPELINE.md](docs/PIPELINE.md). Don't edit these files by hand. Rerun the export, then:
- run `scripts/validate_universe.py`
- give a reason for every mismatch it reports
- include the report's summary line in the pull request
