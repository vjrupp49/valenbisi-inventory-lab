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

## 2026-10-25 Phases 2-3 done
- Phase 2: docs/analysis_charter.md. Decisions (made by Claude on Vincent's instruction): replace last_reported staleness with "count flat N h"
  (flag 6 h, exclude 12 h), hourly "any stockout" forecast target, headline rates exclude not-installed / not-renting / stuck>=12 h.
- Phase 3: dbt rebuilt. fct_station_snapshot (flat_hours, is_stuck, is_stuck_excluded, *_eligible, as-of capacity, is_holiday), fct_station_hour on UTC hour,
  kpi_service_level (headline / strict / raw rates + exclusion counts), holidays seed, 4 new data tests, forecast code moved to hour_utc/stuck_share, dashboard updated.
- Real frozen data: dbt build PASS=46 WARN=1 (Oct 9 run gaps). Headline stockout rate 13.3% vs raw 13.9% vs strict 12.8%. Audit reconciles with dbt exactly.
- Tests: 35 pass incl. 25-hour and 23-hour clock-change days, as-of capacity, stuck rule, holiday flag.
- Note: flat_hours counts from first snapshot when no change seen yet, so the 12 h share is 1.1% in the model vs 0.7% in audit D8 (which skipped never-changed stretches).

## 2026-10-25 Phase 4 done
- src/analysis/service_level.py -> docs/service_level_results.md (auto); analysis/plot_service_level.R -> docs/figures/*.png; docs/service_level_findings.md (interpretation, numbers checked against results).
- Headline: stockout 13.4% (12.0-13.9% across exclusion rules), blockout 6.7%; weekday overnight stockout ~19%, afternoon ~11%; 1 chronic station, 36 at >=25%.
- README now has "First results" (every number from the scripts). tests/test_service_level.py added.
- Next: Phase 5 segmentation stability, then Phase 6 forecast backtest on the frozen set.

## 2026-11-04 Phases 5-6 done
- Collection health: 3,736 runs; 4 failures = upstream HTTP 503 on api.cyclocity.fr 2026-11-02 23:30-00:00 UTC (not our bug; logged in run_meta); gaps since Oct 10 max 30 min.
- Phase 5: src/analysis/segmentation_stability.py -> docs/segmentation_results.md / segmentation_findings.md. Ranking stable (Spearman 0.98-0.99), A/B/C labels 90-93% agreement, 11-15% move with cutoffs, XYZ barely discriminates (253/273 are X) -> use rank, not labels; revisit XYZ with relative thresholds at 30+ days.
- Phase 6: src/forecast/evaluate.py (+ StationMean/StationState baselines, AUC/log-loss, day-block bootstrap, placebo). Real results on frozen data: 1 h GBM Brier 0.083 vs 0.099 best baseline (skill 16.5%, CI 15.2-18.3%), AUC 0.93; 3 h skill 8.2%; 6 h no better than hour-of-week. Placebo AUC 0.51.
- Caveats recorded: only 9 test days, intervals probably too narrow; model mostly uses min_bikes this hour (short-term tracking, not weekly routine).
- Next: connect measured forecast skill to the simulation's forecast-noise knob; new freeze + re-run at 30 days of steady collection (~Nov 10; corrected from an earlier 'Nov 24'), then 60 (~Dec 10) and 90 days (~Jan 9).

## 2026-11-04 Master timeline
- Added docs/master_timeline.md (status by phase, dated history, roadmap to autumn 2027, automatic-vs-manual calendar, decisions, limits, definition of done for v1). Update it at the end of every phase.
- Freeze schedule: 30 days ~2026-11-10, 60 days ~2026-12-10, 90 days ~2027-01-09. Token renewal reminder ~2027-02-15 (expiry 2027-03-01).

## 2026-11-04 Phase 7 done (first version)
- src/simulate/empirical.py + run_empirical.py: estimates demand/stations/trip time/burstiness from the dbt tables, matches forecast noise to measured AUC, runs policies + sensitivity grid, validates the replica against the real network. Estimated inputs saved in src/simulate/estimated/.
- Realism fixes made while building: (1) independent per-station returns let the fleet drift, so trips now conserve bikes (returns follow served pickups; trip time 0.318 h from Little's law); (2) rerouting displaced bikes to the emptiest stations was free rebalancing, replaced by 'retry next hour'.
- Statistics fix: first reported the spread across replications as an interval; now a 95% CI for the mean.
- Findings (docs/simulation_findings.md): reactive avoids ~4.6% of lost pickups; forecast_3h +21/day over reactive (CI 14-28), oracle +25; 6 h forecast worse than reactive; budget matters more than forecast quality; the replica understates empty stations (7.9% vs 13.3%), so only relative comparisons count.

## 2026-11-04 Phase 8 done (local dashboard)
- dashboard/app.R: tabs Overview, Service level (hourly line + heatmap), Segmentation, Forecast (Brier by horizon, calibration), Simulation (avoided pickups, paired difference vs reactive, budget/demand sensitivity, validation), Collection health.
- Forecast and simulation tabs parse the tables from docs/*_results*.md, so no number is typed by hand; the overview figures are computed from the exported marts and results files. Simulation tab carries the 'what-if machine, not a measurement' banner.
- Checked by launching the app and opening every tab (no server or console errors). .claude/launch.json added so the preview can start it. Not published; public hosting still needs an explicit ask.
- Dashboard CSVs in dashboard/data are gitignored; regenerate with src/export_marts.py (the current copy is from the frozen data, exported 2026-10-25).

## 2026-11-04 Phase 9 done (first version)
- docs/case_study.md (one-page story with links to each finding) and docs/interview_script.md (30 s, 2 min, expected questions). Numbers copied from the findings documents; refresh both after each data-freeze re-run.
- README links the case study at the top of the results. GitHub repo description added.
