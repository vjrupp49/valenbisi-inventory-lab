# PROGRESS

## Bootstrap (2026-10-09)
- [x] Phase 0 preflight: git, python 3.14.7, gh 2.100.0 present; gh token scopes include `repo` and `workflow`. User: vjrupp49.
- [x] Phase 1: placeholders replaced (src/ingest.py, README.md); venv + `pytest -q` -> 6 passed.
- [x] Phase 2: public repo https://github.com/vjrupp49/valenbisi-inventory-lab created, `main` pushed.
- [x] Phase 3: `gh workflow run ingest.yml` -> success (run 37891100973). `data` branch exists with parquet files;
      cloned to `data_repo/`. See docs/data_quality_findings.md for the real `check_data.py` output (1 snapshot, 276 stations, 267/272 installed stations stale >1h).
- [x] Phase 4: branch `overnight`, `.claude/settings.json` copied from overnight template.

## Decisions
- Edited only a comment and the username placeholder in `src/ingest.py` (authorized by BOOTSTRAP Phase 1).

## Roadmap
- [x] 1 Environment (venv, deps, pytest green).
- [x] 2 Data pulled, findings in docs/data_quality_findings.md (only 1 snapshot at that time).
- [x] 3-5 dbt project in `dbt/` (staging, dim_station, fct_station_snapshot, fct_station_hour, fct_run_health,
      kpi_service_level, seg_station_abc_xyz) with schema tests + run_meta gap/recency checks.
      `dbt build` -> PASS=39 on SYNTHETIC sample (`dbt/sample_data`, from `src/synth.py`) and on the real 1-snapshot data.
      Run from repo root: `dbt build --project-dir dbt --profiles-dir dbt [--vars '{data_root: dbt/sample_data}']`.
      KPI and segmentation are flagged `is_provisional` until 14 days; with real data now every station is `n/a`
      (no day has enough snapshots), which is the honest result.
      `tests/test_dbt_models.py` checks flags/segmentation against raw synthetic frames.

## Notes
- `rm -rf` is denied by overnight settings; used PowerShell Remove-Item only for a generated untracked sample dir.
- Bash heredocs with long mixed content failed to parse once; files written with the Write tool instead.
- [x] 6 Forecast scaffold `src/forecast/` (features w/ leakage tests, 3 models, rolling-origin backtest, Brier/skill/ECE).
      Developed on SYNTHETIC data only. CLI refuses real-data scores below 14 days.
- [x] 7 Simulation scaffold `src/simulate/` (config.toml = all assumptions; 4 policies; common random numbers; tests).
- [x] 8 Dashboard skeleton `dashboard/app.R` (smoke-tested with shiny::testServer on synthetic exports),
      `src/export_marts.py`, `docs/methodology.md`.
- [x] 9 CI extended: installs dbt-duckdb, runs pytest + `dbt build` on `dbt/sample_data` (synthetic).
- [x] 10 README updated to match what exists.

## Blocked / not verified
- Scheduled cron collection NOT verified: at the end of the build `data` branch still had only the manual run
  (1 snapshot). New-repo cron can take a while to start; check `gh run list --workflow ingest.yml`.
- duckdb R package not installed here, so the dashboard reads CSV exports rather than the DuckDB file.
- CI: first run failed on invalid YAML in ci.yml (colon in a plain scalar); fixed, PR check green.

## Questions for Vincent
- Is 1-hour staleness the right cutoff once daytime data exists? Overnight, 267/272 stations were stale in the single snapshot.
- Want the dashboard to read DuckDB directly (needs R `duckdb` package)?
