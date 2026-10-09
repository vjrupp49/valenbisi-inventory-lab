# Valenbisi Inventory Lab

![ingest](https://github.com/vjrupp49/valenbisi-inventory-lab/actions/workflows/ingest.yml/badge.svg) ![ci](https://github.com/vjrupp49/valenbisi-inventory-lab/actions/workflows/ci.yml/badge.svg)

Treating Valencia's bike-share stations as **inventory nodes**: bikes are stock, an empty or full
station is a stockout, and rebalancing trucks are replenishment. This project collects the live
feed continuously, models it in SQL (DuckDB + dbt), forecasts stockouts, and simulates which
rebalancing policy would have prevented the most of them.

> **Status: data collection started; modeling, forecasting and simulation scaffolds exist but are
> developed and tested on synthetic data only.** No forecast score, segment or key result from real
> data is reported here, because the collected history is still far too short (see
> [docs/data_quality_findings.md](docs/data_quality_findings.md)).

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
- **`last_reported` can be old.** Many stations show last-reported times hours behind the feed
  timestamp, so a station's count may be stale rather than unchanged. `run_meta.n_stale_1h`
  tracks this and the modeling layer must handle it.
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
- [ ] Real forecasting results (needs 14+ days of data)
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
