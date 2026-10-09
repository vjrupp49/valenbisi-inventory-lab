# Valenbisi Inventory Lab: instructions for Claude Code

## Mission
Portfolio project for a data/analytics job search (remote analytics, ops and analytics-engineering
roles). Treat Valencia bike-share stations as inventory nodes (bikes = stock, empty/full = stockout,
rebalancing = replenishment). Collect the live Valenbisi GBFS feed, model it in SQL (DuckDB + dbt),
then forecast stockouts and simulate rebalancing policies. Quality and honesty matter more than scope.

## Hard rules (never break these)
1. **Never touch `main` directly.** Work on branch `overnight`; push only `origin overnight`.
   The scheduled collector runs from `main`, and a broken `ingest.yml` or `ingest.py` silently stops data collection.
2. **Do not edit `.github/workflows/ingest.yml` or `src/ingest.py`** unless fixing a proven bug,
   with a test that fails before the fix and passes after. Note it in PROGRESS.md.
3. **No fabricated results.** Never put a number, chart, finding or "key result" in the README or any
   doc unless a script in this repo produced it from real collected data. Short history is a
   limitation to state, not hide. Use synthetic data only for tests and clearly label it.
4. **No secrets, tokens or personal data** in files, logs or commits.
5. **No force-pushes, no deleting branches/repos, no enabling GitHub Pages or other public publishing.**
6. **Respect the data sources:** JCDecaux Open Licence (attribute), Open-Meteo CC BY 4.0. Do not
   increase request frequency or add scraping.
7. Do not read `data_repo/` as if it were source code; it is data.

## Data layout (the `data` branch, cloned locally as `data_repo/`)
- `station_status/dt=YYYY-MM-DD/ts=HHMMSS.parquet`  station x snapshot
- `run_meta/dt=.../ts=....parquet`  one row per run (ok, error, feed_age_s, n_stale_1h, weather)
- `station_information/dt=.../station_information.parquet`  daily
Refresh with: `git -C data_repo pull` (clone with `git clone --branch data --single-branch <repo-url> data_repo` if missing).

## Known data caveats (model around these)
- The feed is live-only; history starts at the first snapshot.
- `last_reported` can be hours older than the feed timestamp, so a station count may be stale, not unchanged.
- No trip data; activity is inferred from changes in bike counts (a lower bound on true trips).
- Some stations are `is_installed = false`; exclude from service-level metrics.
- GitHub cron drifts and skips; use run_meta to measure gaps instead of assuming a regular grid.

## Definition of done for any task
Tests pass (`pytest -q`), `dbt build` passes when dbt models exist, README/docs match what the code
actually does, change committed with a clear message, entry added to PROGRESS.md.

## Working style
- Small, reviewable commits. Commit after every green checkpoint so a crash or usage limit loses nothing.
- Keep PROGRESS.md updated: done, in progress, blocked (and why), decisions made, questions for Vincent.
- If blocked or unsure on something irreversible or ambiguous, write the question in PROGRESS.md,
  skip that item, and continue with the next one.
- Vincent knows R and Quarto well, Python and SQL less; comment non-obvious SQL and keep structure simple.

## Roadmap (do in order; tick off in PROGRESS.md)
1. Environment: venv, `pip install -r requirements.txt dbt-duckdb`; verify pytest green.
2. Pull `data_repo`; run `python src/check_data.py data_repo`; record findings (gap sizes, feed freshness,
   share of stale stations) in `docs/data_quality_findings.md` using ONLY what the output shows.
3. dbt project in `dbt/` (dbt-duckdb reading the parquet): staging models, `dim_station`,
   `fct_station_snapshot`, `fct_station_hour` (availability, stockout/blockout flags, staleness flag),
   plus schema tests (not_null, unique, accepted_values, relationships) and a freshness-style check on run_meta.
4. KPI mart: stockout/blockout rate by station and hour-of-day, with a data-coverage column.
5. Segmentation: ABC (inferred turnover) and XYZ (variability) per station, with documented, tested logic.
   Write it so results are marked provisional until enough days of data exist.
6. Forecasting scaffold in `src/forecast/`: baselines (persistence, hour-of-week) and a gradient-boosted model,
   rolling-origin backtest, Brier score + calibration. Develop against synthetic data; do NOT report real
   model results until at least 14 days of real data exist.
7. Simulation scaffold in `src/simulate/`: parameterized Monte Carlo of static vs forecast-driven rebalancing,
   all assumptions explicit in a config file.
8. Dashboard skeleton (Shiny for R, using existing data marts) and `docs/` methodology outline.
9. CI: extend `.github/workflows/ci.yml` to run `dbt build` against a small committed sample; keep it green.
10. README update reflecting only what exists. Open a PR from `overnight` to `main`; do not merge.
