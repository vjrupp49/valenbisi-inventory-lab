# Analysis charter (Phase 2)

Dated 2026-10-25. Based on the frozen dataset `data-freeze-2026-10-24` and the
[data integrity report](data_integrity_report.md). Vincent delegated the open decisions to Claude on 2026-10-25;
they are recorded here with the reasons, so they can be reviewed or reversed later.

## Decisions
| # | Decision | Reason (evidence) |
|---|---|---|
| 1 | Stop using `last_reported` as the data-quality gate. Use "bike count unchanged for N hours" instead: **flag at 6 h** (`is_stuck`), and **exclude from headline stockout/blockout rates at 12 h**. Show the 6 h version as a stricter sensitivity result. `last_reported` stays in the tables as an informational age column. | Counts changed in 209,303 intervals but `last_reported` moved in only 3.5% of them (C3b); the 1-hour rule flagged 93.6% of readings (C2). Flat >= 6 h covers 3.3% of readings and >= 12 h covers 0.7% (D8): small enough to be informative, large enough to catch the stuck stations (D7). |
| 2 | Forecast target = **"any stockout at this station in the next clock hour"**, not "stockout at the next snapshot". | A third of stockout episodes last one snapshot (D5); an hourly "any" target is less sensitive to which 10-minute instant we happened to sample, and it is the useful operational question. |
| 3 | Headline stockout/blockout rates use only rows that are installed, **renting** (stockouts) or **returning** (blockouts), and **not stuck >= 12 h**. Always report how many rows were excluded. Raw and strict versions stay available. | 5 not-installed stations, 1,992 not-renting snapshots, and stations stuck for ~95 h would otherwise distort the rates (B1, B5, B6, D7). |
| 4 | Hourly tables are keyed on the **UTC hour**, with the Madrid hour kept as an attribute. | Clock change on 2026-10-25 repeats a local hour (A8); next one skips an hour on 2027-03-28. |
| 5 | Station capacity is looked up **as of the snapshot date**, and `bikes / capacity` is called an approximate fill ratio, not a precise one. | Station 16 changed capacity (B4); 13.0% of rows do not add up to capacity (B2). |
| 6 | Add a small holiday calendar and a holiday flag; do not infer holiday effects yet. | Oct 9 and Oct 12 fall in the window; effects cannot be estimated from a few days. |

## Verdicts: what we will and will not do
| Analysis | Verdict | Conditions |
|---|---|---|
| Availability by hour and weekday | **Do** | Use the 15 full days; say it is two weekly cycles |
| Stockout / blockout rates by station and hour | **Do, with caveats** | Headline rates per decision 3; show raw and strict versions; stockout rate is a lower bound because short episodes are missed |
| Chronically empty / full stations | **Do** | Report separately from peak-hour stockouts |
| ABC/XYZ segmentation | **Do, provisional** | Activity is a lower bound; test stability (split-half, threshold changes); label provisional until 14 usable days per station and re-run at 30/60/90 days |
| 1-hour-ahead stockout forecast | **Try, report honestly** | Time-ordered backtest, baselines first, uncertainty intervals; "no better than the baseline" is an acceptable result |
| Rebalancing simulation | **Do, assumption-driven** | Estimate demand shape from data where possible; keep truck behaviour as labelled assumptions; add sensitivity analysis |
| Weather effect | **Not yet** | Only 3 light rainy days |
| Holiday, seasonal and event effects | **No** | Too short |
| True trips, demand, revenue | **No** | No trip data (inferred changes are a lower bound) |
| Effect of real rebalancing | **No** | No truck data; the 06:00 UTC jumps are a hypothesis only |

## Success criteria for the next phases
- **Phase 3 (data layer):** `dbt build` passes on real data and on the synthetic sample; new tests prove the clock-change handling, the stuck-station rule and the as-of capacity; raw-versus-model reconciliation still matches exactly.
- **Phase 4 (descriptive analysis):** every chart or table states days covered and rows excluded.
- **Phase 6 (forecast):** reported only against baselines, with intervals; if it does not beat the hour-of-week baseline out of sample, we say so.
- Nothing is reported that a script in this repo did not produce from the frozen dataset.

## Revisit triggers
Re-run the audit and reconsider these decisions when: 30 days of data exist; a rainy week occurs; a school-holiday week occurs; or `last_reported` behaviour visibly changes.
