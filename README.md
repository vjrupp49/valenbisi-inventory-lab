# Valenbisi Inventory Lab

![ingest](https://github.com/vjrupp49/valenbisi-inventory-lab/actions/workflows/ingest.yml/badge.svg) ![ci](https://github.com/vjrupp49/valenbisi-inventory-lab/actions/workflows/ci.yml/badge.svg)

Treating Valencia's bike-share stations as **inventory nodes**: bikes are stock, an empty or full
station is a stockout, and rebalancing trucks are replenishment. This project collects the live
feed continuously, models it in SQL (DuckDB + dbt), forecasts stockouts, and simulates which
rebalancing policy would have prevented the most of them.

> **Status: data collection live.** Analytics, forecasting and the dashboard are being built in
> public. See the roadmap below. Nothing on this page claims a result I have not produced yet.

## Why this project
Inventory theory (ABC/XYZ segmentation, safety stock, service levels) transfers directly to
bike-share operations, and a public live feed makes it checkable by anyone.

## Architecture (current)

```
Valenbisi GBFS v3  ─┐
                    ├─► GitHub Actions (every ~10 min) ─► Parquet snapshots ─► `data` branch
Open-Meteo weather ─┘        src/ingest.py                 (Hive-partitioned)
```

Planned: DuckDB + dbt models (staging → intermediate → marts) → forecasting + simulation →
Shiny dashboard + dbt docs site.

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
- [ ] DuckDB + dbt staging/marts with tests and docs
- [ ] Service-level KPIs (stockout/blockout rates by station and hour)
- [ ] ABC/XYZ station segmentation
- [ ] Stockout forecasting with rolling-origin backtests (Brier score, calibration)
- [ ] Rebalancing-policy Monte Carlo simulation
- [ ] Weather and event effects (permutation tests, FDR correction)
- [ ] Public dashboard

## Run locally
```bash
pip install -r requirements.txt
pytest -q
python src/ingest.py --out data_repo      # one live snapshot
```

## Attribution
Station data: Valenbisi / JCDecaux, JCDecaux Open Licence. Weather: Open-Meteo.com (CC BY 4.0).
Code: MIT.
