# Valenbisi Inventory Lab

![ingest](https://github.com/vjrupp49/valenbisi-inventory-lab/actions/workflows/ingest.yml/badge.svg) ![ci](https://github.com/vjrupp49/valenbisi-inventory-lab/actions/workflows/ci.yml/badge.svg)

Treating Valencia's bike-share stations as **inventory nodes**: bikes are stock, an empty or full
station is a stockout, and rebalancing trucks are replenishment. This project collects the live
feed continuously, models it in SQL (DuckDB + dbt), forecasts stockouts, and simulates which
rebalancing policy would have prevented the most of them.

> **Status: collecting continuously; first descriptive results and a data-integrity audit are done.**
> Forecasting, segmentation and simulation exist as tested scaffolds but have **no real-data results yet**
> (about two weeks of data so far). Everything below comes from scripts in this repo on a frozen dataset.

## First results (frozen dataset, 15 complete days; details and caveats in [docs/service_level_findings.md](docs/service_level_findings.md))
- Stations are empty about 13% of the time and full about 7% of the time (stockout rate 13.4% headline, 12.9% to 13.9% depending on how stuck readings are treated; blockout 6.7%). Stockouts are lower bounds because stockouts shorter than the 10-minute sampling can be missed.
- Strongly time-of-day dependent: on weekdays about 19% of stations are empty around 02:00 and about 11% mid-afternoon; about 16% are full at 03:00 and about 2% at 15:00.
- Concentrated: 1 of 272 stations is empty at least half the time, 36 at least a quarter; 21 more stations are empty over half the time in specific hours.
- Data caveat that changed the method: the feed's `last_reported` field barely moves when bike counts do, so data quality is judged by how long a count has been frozen instead ([docs/data_integrity_report.md](docs/data_integrity_report.md)).
- Only two weekly cycles in one autumn month: no weather, holiday or seasonal conclusions.

## Why this project
Inventory theory (ABC/XYZ segmentation, safety stock, service levels) transfers directly to
bike-share operations, and a public live feed makes it checkable by anyone.

## Architecture

```
Valenbisi GBFS v3  -+
                    +-> GitHub Actions (cron */10) -> Parquet snapshots -> `data` branch
Open-Meteo weather -+        src/ingest.py            (Hive-partitioned)
                                                           |
                  dbt + DuckDB (dbt/): staging -> dim/fct -> KPI + ABC/XYZ marts
                                                           |
          src/forecast (baselines, GBM, rolling-origin backtest)    dashboard/ (Shiny skeleton)
          src/simulate (Monte Carlo rebalancing policies)
```

What exists: ingestion with tests; dbt project with 39 passing checks on a synthetic sample (and on the
real data, which is one snapshot so far); stockout/blockout KPI mart and ABC/XYZ segmentation (both
flagged provisional until 14 days); forecasting scaffold; assumption-driven simulation scaffold;
a Shiny dashboard skeleton fed by CSV exports. Method details: [docs/methodology.md](docs/methodology.md).

## Data
| Table | Grain | Notes |
|---|---|---|
| `station_status/` | station x snapshot | bikes, docks, disabled counts, flags, `last_reported` |
| `run_meta/` | one row per run | HTTP status, latency, feed age, stale-station count, current weather, errors |
| `station_information/` | station x day | name, coordinates, capacity (fetched once a day) |

Snapshots live on the `data` branch to keep `main` clean:

```bash
git clone --branch data --single-branch https://github.com/<you>/valenbisi-inventory-lab data_repo
python src/check_data.py data_repo     # health report: gaps, errors, feed freshness
```

## Known limitations (stated up front)
- **Live feed only.** There is no public history, so analysis starts from the first snapshot.
- **No trip data.** Activity is inferred from changes in bike counts, which understates true trips
  (a bike out and a bike back between snapshots is invisible).
- **`last_reported` is not a freshness signal.** Many stations show last-reported times hours behind the feed
  timestamp, yet their bike counts keep changing (see [docs/data_integrity_report.md](docs/data_integrity_report.md)).
  Data quality is therefore judged by how long a station's count has been unchanged instead.
- **GitHub cron is best-effort.** Runs drift and can be skipped. Gaps are measured in `run_meta`.

## Roadmap
- [x] Ingestion pipeline + tests + CI
- [x] DuckDB + dbt staging/marts with schema tests (synthetic sample in CI)
- [x] Service-level KPI mart (stockout/blockout by station and hour, with coverage columns)
- [x] ABC/XYZ segmentation (provisional until 14 days)
- [x] Forecasting scaffold: persistence, hour-of-week, gradient boosting, rolling-origin backtest, Brier + calibration
      (real scores withheld until >= 14 days; the CLI enforces this)
- [x] Rebalancing Monte Carlo scaffold (all assumptions in `src/simulate/config.toml`)
- [x] Dashboard skeleton (Shiny; needs R with shiny, ggplot2, dplyr)
- [x] Data integrity audit and frozen dataset ([report](docs/data_integrity_report.md))
- [x] Descriptive service-level results ([findings](docs/service_level_findings.md))
- [ ] Real forecasting results (scaffold ready; to be run against the frozen dataset next)
- [ ] Simulation parameters estimated from real data
- [ ] Weather and event effects (permutation tests, FDR correction)
- [ ] Public dashboard

## Run locally (Python 3.11+)
```bash
python -m venv .venv && source .venv/bin/activate        # Windows: .venv/Scripts/activate
pip install -r requirements.txt -r requirements-dbt.txt
pytest -q

# model the data (real data in data_repo/, or the SYNTHETIC sample)
dbt build --project-dir dbt --profiles-dir dbt --vars '{data_root: dbt/sample_data}'
dbt build --project-dir dbt --profiles-dir dbt                 # uses data_repo/

# reproduce the audit and the descriptive results on the frozen dataset (see docs/dataset_card.md)
python src/audit/run_audit.py --data data_frozen --out docs/data_integrity_results.md --dbt-db dbt/target/valenbisi.duckdb
python src/analysis/service_level.py --db dbt/target/valenbisi.duckdb --out docs/service_level_results.md
Rscript analysis/plot_service_level.R

# synthetic-data development of the forecaster, and the simulation
python src/forecast/run.py --db dbt/target/valenbisi.duckdb --synthetic
python src/simulate/run.py

# dashboard (uses CSV exports of the marts)
python src/export_marts.py --db dbt/target/valenbisi.duckdb --out dashboard/data
Rscript -e 'shiny::runApp("dashboard")'
```
On Windows consoles set `PYTHONUTF8=1` before running `src/check_data.py`.

## Attribution
Station data: Valenbisi / JCDecaux, JCDecaux Open Licence. Weather: Open-Meteo.com (CC BY 4.0).
Code: MIT.
