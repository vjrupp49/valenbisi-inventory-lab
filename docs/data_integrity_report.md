# Data integrity report (Phase 1)

Dataset: frozen `data-freeze-2026-10-24` (see [dataset_card.md](dataset_card.md)).
Numbers: all from `src/audit/run_audit.py`, shown in full in [data_integrity_results.md](data_integrity_results.md)
(check IDs like **C3** point to the table there). Anything marked **Hypothesis** is a guess to test, not a finding.
Times are UTC; Madrid was UTC+2 during this period.

## The short version
1. **Collection is solid.** 2,168 snapshots, no failed runs, no duplicates, no missing values, and our own cleaned tables match the raw data exactly.
2. **Bike counts look live, but our "stale" flag is useless.** The `last_reported` field barely moves when bike counts do, so flagging 94% of station readings as stale (the 1-hour rule) throws away information instead of protecting us. This changes how we define data quality (Phase 3).
3. **Stockouts are common and short.** About 14% of station readings are at zero bikes, and a third of stockout episodes appear in only one 10-minute snapshot, so shorter ones are probably missed.
4. **The real limit is time, not data quality.** Fifteen full days, one autumn month, two weekly cycles, and only 3 rainy days. That caps what we can claim, whatever the data quality.

## A. Completeness: did we capture what we think?
| Question | Answer (check) |
|---|---|
| How much data? | 599,742 station rows in 2,168 snapshots across 277 stations, 2026-10-09 05:58 to 2026-10-24 23:50 (A1) |
| Is the schedule steady? | Yes since the timer: each of the 15 full days has 142 to 145 snapshots against 144 expected (A2). Median gap 10 min, 99th percentile 10.75 min (A3) |
| Gaps? | Five gaps over 15 min. Three are Oct 9 (427, 422 and 174 min), before the timer. Two since: 20 min on Oct 14 and 29.9 min on Oct 23 (A3b) |
| Failed runs, orphan files? | None: 2,168 runs, all ok, each with station rows and vice versa (A5) |
| Duplicates, null values, wrong folder dates? | None of each (A6) |
| Was a stale copy of the feed served twice? | No repeated feed timestamps and no identical consecutive snapshots (A7) |
| Do stations appear or vanish? | One station (id 18) appears on Oct 15 at 10:50, taking the count from 276 to 277; it is marked not installed in all 1,374 snapshots it appears in (A4, B5, B7) |
| Does the clock change break us? | Yes, on live data. On 2026-10-25 Madrid hour 2 happens twice, so two different real hours get the same local-hour label (A8). Our hourly table is built on the local label, so those two hours would be merged. The frozen set stops before this date, so it is not affected. |

## B. Validity: do the values make sense?
- **No impossible values:** no negative counts, and bike types always add up to the total (B3).
- **Flags:** 273 stations are normal (installed, renting, returning). 5 stations are never or mostly not installed (ids 70, 300, 501 always; 16 for 2,027 of 2,168 snapshots; 18 always), and they show 0 bikes (B1, B5). 58 stations have spells of "installed, not renting but accepting returns": 1,992 station-snapshots (0.3% of rows), during which counts barely change (change rate 1.3%, versus 35.6% normally) (B6, C3b). These are real out-of-service periods and must not be counted as stockouts. Our rules already require "renting" for a stockout, which handles this.
- **Capacity arithmetic:** bikes plus free docks equals the station's capacity in 381,075 of 589,837 installed rows (64.6%). Adding disabled bikes and docks raises that to 513,255 (87.0%). In the remaining 76,575 rows (13.0%) some spaces are unaccounted for, usually by 1 (median gap 0, 90th percentile 1) (B2). **Consequence:** do not treat `bikes / capacity` as a precise fill level. Disabled bikes are in 16.3% of rows and disabled docks in 12.5%, up to 20 at a station (B3).
- **Metadata:** only one station changed capacity: station 16, from 20 to 16 on Oct 15 (B4). Locations show rounding noise of about 5 cm only. We should use the capacity valid on the day, not the latest.

## C. Freshness: is `last_reported` trustworthy? (biggest finding)
- The feed's own timestamp is fresh (feed age at collection: median 0.6 s, 99th percentile 46.4 s, maximum 115.7 s) (A7b), but `last_reported` per station is old: median age 9.0 hours, 90th percentile 21.8 hours (C1).
- Share flagged stale depends heavily on the threshold: 97.2% at 30 min, 93.6% at 1 h, 80.5% at 3 h, 64.9% at 6 h, 37.3% at 12 h, 5.0% at 24 h (C2). Our current 1-hour rule flags almost everything.
- **Bike counts change while `last_reported` does not.** In 209,303 station intervals where the bike count changed, `last_reported` moved in only 7,383 (3.5%) (C3, C3b). The overall count changes in 35.6% of 10-minute intervals.
- **Hypothesis:** `last_reported` mostly gets refreshed in a daily batch, not when a station reports. Support: `last_reported` moves 4,329 times in the 04:00 UTC hour versus 121 to 926 in any other hour, and only 27% of readings are older than an hour at that hour versus 90% to 98% at other hours (C4). Not proven.
- **What this means:** the bike counts themselves appear to be live (they move at a daily rhythm that peaks in the evening, D3). The 1-hour flag does not tell us when a reading is out of date, so we should stop using it as the quality gate. We cannot prove the counts are accurate, because we have no ground truth.
- **Better quality signal to test:** "count has not changed for at least N hours" (D8). It is 23.9% of readings at 1 h, 9.7% at 3 h, 3.3% at 6 h, 0.7% at 12 h and 0.2% at 24 h. A threshold around 6 to 12 hours picks out a small, plausible set of stuck stations. Stations 105, 106 and 112 stayed at 0 bikes for about 95 hours (D7), almost certainly out of service while still marked installed and renting.

## D. Is there enough signal and resolution?
- **Counts move a lot:** the median installed station changes count 794 times in the period (10th to 90th percentile 361 to 1,126); only one station never changed (D1). Activity is spread out, not dominated by a few stations (top 10% of stations account for 15.5% of changes) (D1).
- **Changes are small:** 65% are one bike, and 86% are one or two (D2). Daily shape: change rate rises from 0.085 at 02:00 UTC to 0.54 at 17:00 UTC (D3).
- **Stockouts:** 13.9% of installed, renting station-snapshots are at zero bikes; blockouts (no free dock) are 6.7%; 270 of 273 stations had at least one stockout (D4).
- **They are short:** 14,572 stockout episodes, median 2 consecutive snapshots (about 20 min), 90th percentile 12. 4,806 (33%) show up in a single snapshot, so episodes shorter than 10 minutes are probably missed entirely (D5). Ten episodes last at least a day, three at least three days.
- **Chronic stations:** 1 station is empty at least 90% of the time, 3 at least 50%, 38 at least 25% (D6). Some of these are "structurally empty", which is a different problem from peak-hour stockouts.
- **Hypothesis (rebalancing):** jumps of 8 or more bikes in one step cluster at 06:00 UTC (122 upward jumps versus 52 at most in any other hour, with a smaller bump at 13:00 UTC) (D9), which looks like trucks restocking. There is no truck data, so we cannot confirm.

## E. Weather and F. Calendar
- Weather is one city-wide reading. 4 of 2,168 runs lack it; temperatures 12.1 to 27.6 °C (E1). It rained on only 3 UTC days (Oct 17 to 19, up to 2.3 mm per reading) (E2). Too little variation to estimate a rain effect reliably.
- 15 full days: each weekday twice, Saturday three times (F1). Possible Spanish holidays in the window (Oct 9 regional day, Oct 12 national day) are **not checked here**; treat Oct 9 (partial) and Oct 12 as possibly atypical.
- One autumn month only: nothing about summer, winter, school holidays or festivals.

## G. Do our own models tell the truth?
- Rows, stockouts, blockouts and installed rows from the dbt table match the raw data exactly: 599,742 rows, 81,497 stockouts, 39,634 blockouts, 589,837 installed rows (G1).
- `dbt build` on the frozen data: 38 tests pass and 1 warns (the run-gap warning about the three Oct 9 gaps).

## What we can and can't do (preliminary, for the Phase 2 charter)
| Analysis | Verdict | Why |
|---|---|---|
| Availability by hour and weekday | **Can do** | Counts are live and plentiful; use two full weekly cycles |
| Stockout and blockout rates by station/hour | **Can do with caveats** | Short stockouts are under-sampled; exclude not-renting spells and stuck stations; report coverage |
| Finding chronically empty/full stations | **Can do** | Clear in the data (D6) |
| Segmentation (ABC/XYZ) | **Can do with caveats** | Activity is a lower bound; 15 days gives a rough, provisional ranking; test its stability |
| Stockout forecast, 1 hour ahead | **Can do with caveats** | 14,572 episodes is enough to try, but short history and short episodes limit accuracy; must beat baselines out of sample; report uncertainty |
| Rebalancing simulation | **Can do, assumption-driven** | Demand shape can be estimated from data; truck behaviour cannot |
| Weather effect | **Cannot do reliably yet** | 3 light rainy days |
| Holiday, seasonal, event effects | **Cannot do** | Too short |
| True trips, demand, revenue | **Cannot do** | No trip data; changes are a lower bound |
| Real-world rebalancing effects | **Cannot do** | No truck data |

## Holes register: what is wrong and what we do about it
| # | Hole | Size | Response |
|---|---|---|---|
| 1 | `last_reported` is not a freshness signal | 93.6% flagged stale at 1 h; counts change without it moving | Stop using it as the quality gate. Test "no count change for N hours" instead (Phase 3). Keep `last_reported` as a column only |
| 2 | Stuck stations still marked installed/renting | e.g. 3 stations flat for about 95 h at 0 bikes | Flag and exclude from stockout stats; report how many are dropped |
| 3 | Not-renting and not-installed spells | 5 stations never or mostly installed; 58 stations with 1,992 not-renting snapshots | Already excluded from stockouts; keep exclusion visible |
| 4 | Short stockouts missed at 10-minute sampling | 33% of episodes are one snapshot long | State stockout rates as a lower bound; consider "any stockout in the hour" as the forecast target |
| 5 | Capacity arithmetic does not fully add up | 13.0% of rows below capacity after disabled counted | Avoid precise fill ratios; use counts and flags |
| 6 | Capacity changes over time | station 16 (20 to 16) | Use capacity valid at the time |
| 7 | New station appears mid-period | station 18 on Oct 15 | Treat as a new station; it is not installed anyway |
| 8 | Clock changes: a repeated hour on Oct 25 2026, a skipped hour on Mar 28 2027 | one hour label shared by two real hours (Oct); a local hour with no data (Mar) | Build the hourly table on UTC hours; keep local hour as an attribute (Phase 3) |
| 9 | Collection gaps | Oct 9: 3 long gaps; since: 2 gaps of 20 and 30 min | Existing gap rules (activity ignored across gaps over 30 min) are adequate; keep measuring |
| 10 | Weather too uniform | 3 rainy days | Do not claim weather effects now |
| 11 | Short, single-season window | 15 full days | Say so on every result; re-run at 30, 60 and 90 days |
| 12 | Possible holiday days | Oct 9 and Oct 12 | Check the calendar; flag in Phase 3 if confirmed |

## Decisions I need from you at the Phase 2 gate
1. **Replace the 1-hour staleness flag** with a "count unchanged for N hours" flag (suggest N = 6 hours as the starting point, show results at 3 and 12 as sensitivity)? My recommendation: yes.
2. **Forecast target:** "any stockout in the next hour" (catches short episodes) rather than "stockout at the next snapshot". My recommendation: the hourly version.
3. **Which stations count for headline stockout rates:** exclude the 5 not-installed stations, spells of not renting, and stuck stations (flat 12 hours or more at 0 bikes). My recommendation: yes, and always show the excluded counts.

## What would change this picture
More days, especially more rain, a school-holiday week, and a different season; and any ground truth about whether counts are accurate (for example spot-checking a station against the official app).
