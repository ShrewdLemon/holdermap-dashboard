# Contributing

1. Branch from `main`, edit files in `src/` (`app.js`, `head.html` for CSS, `body.html`).
2. Preview: `python3 build.py && python3 -m http.server 8765 --directory dashboard/site`, open http://localhost:8765.
3. Open a pull request. Merging to `main` publishes the site within a few minutes (AWS CodeBuild runs `buildspec.yml`: JS syntax check, tests, fresh NSE prices, upload).

Do not commit `dashboard/` (build output), `cache/` or `.local/` (access key). Prices come from `pipeline/live.py`; never type a price or a date into `src/app.js`, read it from `NOW` / `OQ` instead.
