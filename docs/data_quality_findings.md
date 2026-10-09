# Data quality findings

Source: `python src/check_data.py data_repo` run on the first collected snapshot
(manual `workflow_dispatch` run, snapshot_ts 2026-10-09 05:58:17 UTC), plus direct DuckDB queries
on that same snapshot. Everything below is from that one snapshot. **There is no history yet**, so
gaps, run cadence, error rates over time and station activity cannot be assessed.

| Check | Observed |
|---|---|
| Runs / ok runs | 1 / 1 (0.0 % errors) |
| Gaps between runs | none measurable (1 run) |
| Feed age at snapshot (`feed_age_s`) | 19.3 s (feed `last_updated` 05:57:57 UTC) |
| Stations in feed / installed | 276 / 272 |
| Installed stations with `last_reported` older than 1 h (`n_stale_1h`) | 267 of 272 |
| Newest `last_reported` across stations | 05:45:12 UTC (about 13 min before snapshot) |
| Median `last_reported` | 03:52:37 UTC (about 2 h before snapshot) |
| Oldest `last_reported` | 2025-07-28 |
| Stations with 0 bikes / 0 docks (all stations, not only installed) | 46 / 34 |
| Total bikes reported | 2006 |
| Stations whose count changed | 0 (not testable with one snapshot) |
| `station_information` rows with null capacity | 0 of 276 |

## Reading
- The feed itself is fresh (19 s), but per-station `last_reported` is not: 267 of 272 installed
  stations had not reported within the hour before the snapshot. The snapshot was taken around 07:58
  Valencia local time, so some of this may be low overnight activity rather than a stale feed. One
  snapshot cannot separate the two; this must be re-checked once daytime snapshots accumulate.
- This confirms the CLAUDE.md caveat: a station count can be stale rather than unchanged, so the
  models carry a staleness flag and do not treat "no change" as "no demand".
- The timestamps print with a `-05` offset in DuckDB because of the local session time zone; the
  stored values are UTC instants.
- `src/check_data.py` crashes on Windows consoles with a cp1252 encoding error unless run with
  `PYTHONUTF8=1`. Not a data problem.

## Update (end of overnight build)
`git -C data_repo pull` and a re-run of `check_data.py` still showed 1 run and 1 snapshot. The only run
so far is the manual `workflow_dispatch` run; no scheduled (cron) run had fired yet, so scheduled
collection is **not yet verified**. Check `gh run list --workflow ingest.yml` and the `data` branch.

## Update 2026-10-09 15:05 UTC (first scheduled run seen)
Source: `check_data.py` after `git -C data_repo pull`: 2 runs, 0 errors.
- Scheduled (cron) collection works: one `schedule`-triggered run succeeded at 13:05 UTC.
- But cadence is far below the nominal 10 minutes: the gap between the two runs is 427 minutes (about 7 h),
  and no other scheduled run happened in that time. Measured by `fct_run_health`, as intended. Whether this
  improves over the next days is unknown; this is a limitation to watch, not a fix we can apply
  (the rules forbid editing `ingest.yml` without a proven bug, or raising request frequency).
- Staleness: 269 of 272 installed stations were still stale (>1 h) at 13:05 UTC, which is mid-afternoon in
  Valencia (about 15:05 local). So the earlier "maybe overnight quiet" explanation is not supported by this
  data point; stale `last_reported` looks common in the daytime too. Two snapshots are still too few to
  conclude why, so the staleness handling in the models stays important.
