# Interview script (one page)

Numbers match [case_study.md](case_study.md). If you re-run the analysis, update both.

## 30-second version
"I treated Valencia's bike stations as inventory. I collected the live feed every 10 minutes, modelled it in SQL with dbt, and asked whether forecasting empty stations would improve rebalancing. Stations are empty about 13% of the time, and an hour-ahead forecast works well, but in a simulation it only beats simply reacting to current counts by under one percent. The number of trucks matters far more. I'm also upfront that it's 15 days from one season."

## 2-minute version
1. **Why:** inventory theory (stockouts, service levels, replenishment) maps directly onto bike-share, and a public live feed lets anyone check the work.
2. **Data:** automated collection every 10 minutes since October, partitioned files, a health check that alerts if collection stalls.
3. **The data problem I found:** the feed's "last reported" time looked like a freshness flag but barely moved when bike counts did, so using it would have discarded 94% of readings. I replaced it with "count unchanged for N hours".
4. **Results:** about 13% of station-time empty, 7% full, with a strong daily pattern and a few stations far worse than the rest. A model predicts an empty station in the next hour with AUC 0.93, 16.5% better on Brier score than the best simple baseline, tested by training only on the past.
5. **So what:** in a simulation of the network, planning with a 3-hour forecast avoids about 21 more lost pickups a day than reacting (interval 14 to 28), under 1%. Budget matters more than forecast quality.
6. **Limits:** 15 days, one autumn month; the simulation understates empty stations, so I only trust comparisons, not absolute savings.

## Questions you should expect
- **Why a rolling backtest, not a random split?** Random splits leak the future into training. Training only on earlier days and predicting the next one is how it would run for real.
- **What is Brier score?** Mean squared error of predicted probabilities; lower is better. Always guessing the base rate (21%) scores about 0.17; the model scores 0.083.
- **What is AUC?** How well it ranks risky station-hours above safe ones; 0.5 is chance.
- **How do you know the model isn't just memorising?** A placebo test (swapping features between stations in the same hour) drops it to chance, and its probabilities are calibrated (when it says 75%, stockouts happen about 74% of the time).
- **Why is the forecast edge small in the simulation?** The model mostly detects "nearly empty and still falling", which reactive rules already capture. Its extra value is a few hours of lead time, and trucks are the bottleneck.
- **Can you trust the simulation?** Only for comparing strategies. It understates empty stations (7.9% versus 13.3% real), and the truck budget and rider behaviour are assumptions. I show sensitivity to both.
- **What mistakes did you catch?** Simulated bikes appearing from nowhere; a rebalancing shortcut that acted as free trucks and flattered every strategy; confidence intervals that measured single-run spread instead of the uncertainty of the average. All logged in docs/PROGRESS.md.
- **What would you do with more time or data?** Re-run at 30, 60 and 90 days; add weather and holidays once enough rainy days exist; add geography (riders detouring to nearby stations) and get real truck data.
- **What did you not do?** No trip data, no truck data, no claim about real savings.

## Words to be able to explain without notes
Stockout and blockout; why `last_reported` was dropped; rolling-origin backtest; Brier score; AUC; calibration; lower bound; what the simulation can and can't show.
