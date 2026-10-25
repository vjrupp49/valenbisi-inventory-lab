# Methodology (outline)

Status: describes what the code does today. Where something is a plan, it says so.

## 1. Data and its limits
- Source: Valenbisi GBFS v3 `station_status` / `station_information` (JCDecaux Open Licence) and Open-Meteo
  current weather (CC BY 4.0), snapshotted by `src/ingest.py` via a GitHub Actions cron (nominally every 10 min;
  actual cadence is measured, see `fct_run_health`).
- No trip data. Activity is inferred from changes in bike counts between consecutive snapshots, and only
  when the snapshots are at most 30 minutes apart. It is a lower bound on true trips.
- `last_reported` is NOT a freshness signal: on the first 15 days it barely moved when bike counts did
  (see `docs/data_integrity_report.md`, section C), so it is kept only as an information column.
  Data quality is judged by whether a station's bike count has been unchanged for a long time: flagged at 6 h
  (`is_stuck`), excluded from headline stockout/blockout rates at 12 h (`is_stuck_excluded`). Decisions and reasons:
  `docs/analysis_charter.md`.
- Short stockouts (shorter than the 10-minute snapshot spacing) can be missed, so stockout rates are lower bounds.
- Findings from the real data so far: `docs/data_quality_findings.md`.

## 2. Modeling layer (dbt + DuckDB, `dbt/`)
| Model | Grain | Purpose |
|---|---|---|
| `stg_*` | as source | rename/cast only |
| `dim_station` | station | latest name, location, capacity; installed flag at the latest snapshot |
| `fct_station_snapshot` | station x snapshot | local time, stuck flags, stockout/blockout (raw and eligible), activity, as-of capacity, holiday flag |
| `fct_station_hour` | station x UTC hour | hourly roll-up used as forecasting features (UTC so clock changes cannot merge or invent hours) |
| `fct_run_health` | collector run | gaps between runs, feed age (the collector's `n_stale_1h` is informational only) |
| `kpi_service_level` | station x hour-of-day | stockout/blockout rates (headline, strict, raw) with coverage columns |
| `seg_station_abc_xyz` | station | ABC/XYZ segmentation |

Definitions: stockout = installed, renting, 0 bikes. Blockout = installed, returning, 0 docks.
Non-installed stations and not-renting spells are excluded from service-level metrics. Headline rates also drop rows
whose count has been flat for 12 h or more. Flat time is counted from the station's last observed change, or from
the first snapshot if none has been seen, so it is a lower bound at the start of the data. Thresholds live in `dbt/dbt_project.yml`.

## 3. Segmentation
- ABC: stations ranked by mean daily inferred activity; A = first 80 % of cumulative activity, B = next 15 %, C = rest.
- XYZ: coefficient of variation of daily activity; X <= 0.5, Y <= 1.0, Z above. Mean zero gives `n/a`.
- Only days with at least 24 snapshots count. Everything is `is_provisional` until 14 usable days exist.
- The cutoffs are conventional defaults, not tuned to this system.

## 4. Forecasting (`src/forecast/`)
- Target: stockout at the same station in the hour `t + h` (default h = 1).
- Features use only hour `t` and earlier (tested for leakage). A missing hour yields a missing lag, never a shifted one.
- Models: persistence, station x hour-of-week mean (with shrinkage), gradient-boosted trees.
- Evaluation: expanding-window rolling-origin backtest, one test day per fold, training labels must end before the
  test day; scored with Brier score, Brier skill against the hour-of-week baseline, and a calibration table.
- Guard: `src/forecast/run.py` refuses to print scores on real data until 14 distinct days exist.
- All development so far used synthetic data (`src/synth.py`); synthetic scores say nothing about real performance.

## 5. Simulation (`src/simulate/`)
- Monte Carlo of pickups/returns per station-hour, with lost demand when empty/full, and four policies
  (none, static route, reactive, forecast-driven) given the same transfer budget and the same demand draws.
- Every parameter, including forecast quality, is an assumption in `src/simulate/config.toml`. Outputs compare
  policies under those assumptions; they are not estimates of real Valenbisi performance.
- Planned: estimate the demand block from real data once enough history exists.

## 6. Not done yet / open questions
- Weather and event effects (needs weeks of data).
- Whether `last_reported` really refreshes in a daily batch (hypothesis from the audit, not proven).
- Plugging the fitted forecaster into the simulator instead of a noise knob.
