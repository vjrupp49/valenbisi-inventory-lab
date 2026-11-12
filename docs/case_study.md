# Case study: treating a city's bike stations as inventory

**One-line summary.** I collected Valencia's live bike-share feed every 10 minutes, cleaned it, modelled it in SQL, and asked whether forecasting empty stations would help rebalance bikes. It helps, but less than you'd expect, and I can say how much and how sure I am.

All numbers below come from scripts in this repo run on a frozen dataset (33 complete days, 272 stations, Oct 10 to Nov 11 2026; the first version of this analysis used the first 15 days, and what changed is noted below). Every figure links to the document that produced it. Results are early: one autumn month, no weather, holiday or seasonal conclusions yet.

## The question
A bike-share network is an inventory problem. Bikes are stock, an empty station is a stockout (a rider can't rent), a full station is a blockout (a rider can't return), and trucks that move bikes are replenishment. Two questions: **how bad is service, and would forecasting stockouts make rebalancing better?**

## What I built
| Layer | What it does | Tools |
|---|---|---|
| Collection | Pulls the public feed every 10 minutes, stores partitioned parquet files; a daily health check raises an alert if collection stalls | GitHub Actions, Cloudflare Worker timer, Python |
| Modelling | Cleans and models stations, snapshots, hourly service level, stuck-reading flags | DuckDB, dbt (with data tests) |
| Analysis | Service level, station segmentation (ABC/XYZ) with stability tests | Python, SQL, R |
| Forecast | Predicts "any stockout in the next hour", with rolling-origin backtest | gradient boosting, bootstrap intervals |
| Simulation | Compares rebalancing strategies on a replica of the network | Monte Carlo |
| Dashboard | Local app to explore all of it | R Shiny |

Quality controls: 50 automated tests, CI on every push, a frozen, tagged dataset so results can be reproduced, and a rule that no number goes into a document unless a script produced it.

## Finding 1: the data needed fixing before anything else
The feed has a per-station "last reported" time, which looks like a freshness signal. It isn't: it changed in only 3.4% of the intervals where a station's bike count changed ([audit](data_integrity_report.md), section C). Using it would have thrown away about 93% of readings as stale. Instead I flagged a reading as stuck when a station's count hadn't changed for 6 hours (12 hours to exclude it), which catches a small, plausible set of broken stations. This changed how every later number is computed.

## Finding 2: service level ([details](service_level_findings.md))
- Stations are empty about 13% of the time and full about 6%.
- Strong daily pattern: on weekdays about 17% of stations are empty around 02:00 and about 10% mid-afternoon.
- Concentrated: 30 of 273 stations are empty at least a quarter of the time.
- These are lower bounds, because stockouts shorter than the 10-minute sampling can be missed.

## Finding 3: segmentation is stable in rank, not in labels ([details](segmentation_findings.md))
Station activity rankings agree at 0.98 to 0.99 (Spearman) between halves of the period, but the A/B/C labels change for 11% to 15% of stations when the cut-offs shift, and the textbook XYZ split barely separates these stations. So I treat the labels as provisional.

## Finding 4: stockouts are forecastable an hour ahead ([details](forecast_findings.md))
Tested honestly: train on past days, predict the next day, move forward, 27 test days.
- 1 hour ahead: Brier 0.082 versus 0.098 for the best simple baseline (16.7% better, 95% interval 15.9% to 17.5%); AUC 0.93; well calibrated.
- A placebo check (features swapped between stations) falls to chance, so the model uses real station state.
- The edge shrinks with lead time: 8% better at 3 hours; at 6 hours it is slightly worse than a simple weekly-pattern average.
- Most of the signal is "this station is nearly empty and still dropping", which is short-term tracking more than long-range prediction.

## Finding 5: forecasts help rebalancing only a little ([details](simulation_findings.md))
I built a replica of the network from the data (real stations, capacities, demand patterns, trip times) and compared strategies on the same simulated riders.
- Reacting to current bike counts avoids about 3.6% of lost pickups (riders who wanted a bike at an empty station).
- Planning with a 3-hour forecast at the measured accuracy beats that by about 33 lost pickups a day (95% interval 26 to 39), roughly 1.3% fewer.
- A 6-hour forecast is worse than just reacting.
- The truck budget matters more than forecast quality: doubling transfers per round (6 to 12) avoids about 56 more lost pickups a day.

## What I would tell a skeptical reader
- **The simulation is a what-if machine, not a measurement.** The replica understates empty stations (7.7% simulated versus 12.8% real), so only comparisons between strategies carry information, and they carry my assumptions (truck budget, timing, how riders react).
- **Short history.** 33 days, one season. Intervals from resampling days are probably too narrow.
- **What changed from 15 to 33 days.** The findings and the ordering of strategies held. The sizes moved: reactive rebalancing's benefit fell from about 4.6% to 3.6% of lost pickups, and the 3-hour forecast's edge rose from about 21 to about 33 pickups a day. So I trust the direction and ranking of results more than the exact sizes. The 15-day results are archived in `docs/archive/`.
- **No trip or truck data.** Activity is inferred from count changes, a lower bound.
- **Mistakes I caught.** An early simulation let bikes appear from nowhere; another version sent bikes to empty stations for free and would have flattered every strategy; my first confidence intervals measured the spread of single runs, not the uncertainty of the average. Each was fixed and is recorded in [PROGRESS.md](PROGRESS.md).

## What's next
Data collection continues, so the analysis re-runs at 60 and 90 days (the 90-day mark is around Jan 9 2027) to see which findings hold and to test holidays and weather. Data: JCDecaux Open Licence; weather: Open-Meteo (CC BY 4.0).
