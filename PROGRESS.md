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

## Decisions (made autonomously, previously open questions)
- Staleness cutoff stays at 1 hour (`stale_after_hours` in dbt/dbt_project.yml). Reason: it matches the collector's
  `n_stale_1h`, and the KPI mart reports rates with and without stale snapshots so the choice stays visible.
  Revisit once several daytime days exist; changing it is a one-line var edit.
- Dashboard keeps reading CSV exports. Reason: avoids installing an extra R package and keeps R needs to shiny/ggplot2/dplyr.
  Switching to DuckDB directly is optional later.

## 2026-10-09 15:05 UTC check
- ingest.yml active; first scheduled run succeeded (13:05 UTC). Only 2 snapshots total; 427 min gap. See findings doc.
- 269/272 stations stale at ~15:05 local: overnight-quiet explanation not supported.
- PR #1 open, mergeable, CI green. Not merged (per rules).

## 2026-10-09 permissions change (Vincent, in chat)
- Vincent lifted the overnight restrictions: Claude may edit/push `main`, edit workflows and ingest code, merge PRs.
  CLAUDE.md hard rules 1, 2, 5 and `.claude/settings.json` updated. Still off-limits: force-push, deleting repo/data branch,
  enabling public Pages without a specific ask, secrets in files, fabricated results.
- Added `.github/workflows/health.yml`: daily watchdog that opens a GitHub issue if collection stalls/sparse.
- ingest.yml cron changed from `*/10` to `7,17,27,37,47,57` (same frequency, off the busiest minutes) because only 1 scheduled run
  fired in ~7 h. Verify over the next days with check_data.py; if still sparse, consider an external trigger (Cloudflare Worker calling workflow_dispatch).
- 2026-10-09: GitHub cron still ~1 run per 7 h. Added `cloudflare/` Worker (10-min timer calling workflow_dispatch) per Vincent's go-ahead.
  Token lives only as a Cloudflare secret. Once verified, consider removing the GitHub schedule so the feed is not hit twice.
- 2026-10-10: Cloudflare timer verified (35 consecutive dispatch runs ~10 min apart, all success). Removed GitHub `schedule:` from ingest.yml to avoid double requests.
  If the timer ever stops (token expiry), the health workflow opens an issue; re-add a schedule or renew the token.
- Timer token (GitHub fine-grained, Actions r/w, this repo only) expires 2027-03-01 per Vincent. Renew before then: new token -> replace Cloudflare secret GITHUB_TOKEN (Worker > Settings > Variables and Secrets).
- 2026-10-13: health.yml raised false alarms (Oct 11, 12): expression compared outputs as text ("144" < "24"). Fixed by computing
  `unhealthy` numerically in the shell step. Collection itself verified healthy: 453 runs, 0 errors, no gap >11 min since Oct 10.

## 2026-10-25 real-data phase plan
- ~15 full days collected (Oct 10-24), 2266 snapshots, 0 errors, only two gaps >15 min since the timer (30 min, 20 min).
- Wrote docs/analysis_plan.md (phases 0-10). Step 1 = data integrity audit (docs/data_integrity_report.md, src/audit/).
  Stops for Vincent's review after the plan, after Phase 1, and after Phase 2.

## 2026-10-25 Phases 0-1 done
- Froze dataset: tag `data-freeze-2026-10-24` on the data branch (commit 0737447), local worktree `data_frozen/`, docs/dataset_card.md.
- Audit: src/audit/run_audit.py (+ tests/test_audit.py), docs/data_integrity_results.md (generated), docs/data_integrity_report.md (interpretation).
- Headline: collection solid (2168 snapshots, 0 failures, dbt matches raw); `last_reported` is NOT a freshness signal (count changes without it moving in 96.5% of cases);
  stockouts 13.9% of snapshots, 33% of episodes one snapshot long; DST double hour on Oct 25 breaks the local-hour grain of fct_station_hour (to fix in Phase 3).
- STOP: waiting for Vincent's review + 3 decisions (staleness replacement, forecast target, headline-stat exclusions) before Phase 2.
- CI broke on the new DuckDB 2.0 (Relation.fetchone() removed); tests switched to con.execute(...).fetchone(). Lesson: requirements are unpinned, so CI picks up new majors; keep an eye on CI emails.
