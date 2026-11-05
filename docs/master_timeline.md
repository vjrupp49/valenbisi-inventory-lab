# Master project timeline and outline

The one page to open when you want to know where the project stands. Update it at the end of every phase.
**Last updated: 2026-11-04.** Repository: https://github.com/vjrupp49/valenbisi-inventory-lab

## 1. The project in one paragraph
Valencia's bike-share system (Valenbisi) treated as an inventory problem: each station is a shelf, bikes are stock,
an empty station is a stockout, a full station is a "blockout" (no free dock), and moving bikes by truck is replenishment.
A GitHub-run collector snapshots the public feed every 10 minutes; SQL models (dbt + DuckDB) turn it into trustworthy
tables; analyses measure service levels, segment stations, forecast stockouts and (next) simulate rebalancing policies.
The goal is a portfolio piece for data, analytics and operations roles, where **honesty about limits matters more than
impressive numbers**.

## 2. Where we are (snapshot, 2026-11-04)
- **Collection:** running automatically since 2026-10-09. 3,756 runs so far, 3,752 successful; 27 UTC days of data. The four failures were an outage on the data provider's side (HTTP 503, Nov 2 to 3).
- **Analysis:** data audit, descriptive results, station segmentation and a first real forecast are done, each with a written findings document.
- **Not yet done:** the simulation using real forecast accuracy, the finished dashboard, the final write-up and interview story, and the 30/60/90-day re-runs.
- **Quality gates in place:** 43 automated tests, continuous-integration checks on every push (green), a daily health check on collection, a frozen reproducible dataset.

### Progress by phase
| # | Phase | Status | Finished | Key document |
|---|---|---|---|---|
| A | Build the collector, repo, CI, models and scaffolds on synthetic data | Done | 2026-10-09 | [README.md](../README.md), [methodology.md](methodology.md) |
| B | Collect data continuously | **Running (never "done")** | started 2026-10-09 | [data_quality_findings.md](data_quality_findings.md) |
| 0 | Freeze a reproducible dataset | Done | 2026-10-25 | [dataset_card.md](dataset_card.md) |
| 1 | Data integrity audit | Done | 2026-10-25 | [data_integrity_report.md](data_integrity_report.md) |
| 2 | Analysis charter (what we will and will not do) | Done | 2026-10-25 | [analysis_charter.md](analysis_charter.md) |
| 3 | Fix the data layer to match reality | Done | 2026-10-25 | [analysis_charter.md](analysis_charter.md) |
| 4 | Descriptive service-level analysis | Done | 2026-10-25 | [service_level_findings.md](service_level_findings.md) |
| 5 | Segmentation (ABC/XYZ) and stability | Done | 2026-11-04 | [segmentation_findings.md](segmentation_findings.md) |
| 6 | Forecast backtest on real data | Done (first version) | 2026-11-04 | [forecast_findings.md](forecast_findings.md) |
| 7 | Rebalancing simulation using measured inputs | **Next** | | `src/simulate/` |
| 8 | Dashboard (local) | Skeleton only | | `dashboard/app.R` |
| 9 | Write-up and interview story | Not started | | |
| 10 | Keep collecting; re-run at 30, 60, 90 days | Planned | first re-run about 2026-11-10 | [analysis_plan.md](analysis_plan.md) |

Rough completion: the analysis core (phases 0 to 6) is done; what remains is the simulation, the presentation layer,
and the long-run re-checks. The re-checks are what turns a two-week snapshot into a year-long study.

## 3. What happened, in order
| Date | Event |
|---|---|
| 2026-10-09 | Overnight build: repo created, collector verified, SQL models, forecast and simulation scaffolds (synthetic data), dashboard skeleton, CI. First data collected. |
| 2026-10-09 | GitHub's own scheduler ran the collector only about once every 7 hours. Restrictions lifted; a daily health check was added; the PR was merged. |
| 2026-10-09 to 10 | Outside timer (Cloudflare Worker) set up and verified; GitHub's own schedule removed to avoid double requests. Collection reached the planned 10-minute rhythm. |
| 2026-10-12 | Health-check false alarms fixed (it compared numbers as text). |
| 2026-10-25 | Frozen dataset (`data-freeze-2026-10-24`). Audit found the feed's `last_reported` field is not a freshness signal. Charter written. Data layer rebuilt (stuck-count rule, UTC hours, as-of capacity, holiday list). First descriptive results. |
| 2026-10-25 | CI broke after a DuckDB major update; fixed. |
| 2026-11-02 to 03 | Provider outage (503) caused 4 failed runs; collection resumed unaided. |
| 2026-11-04 | Segmentation stability and the first real forecast results. This timeline written. |

## 4. What the project has found so far (all from scripts on the frozen 15-day dataset)
- Stations are empty about 13% of the time and full about 7%; strongly time-of-day dependent; concentrated in a few stations.
- The feed's `last_reported` field is unreliable as a freshness signal, which changed our data-quality method.
- Station activity ranking is very stable; the A/B/C labels are softer; the XYZ steadiness split barely separates stations.
- A forecast of "any stockout next hour" beats simple baselines by about 16% on Brier score, with the advantage fading by 3 to 6 hours.
Details and caveats are in the findings documents. Every number must come from a script in this repo.

## 5. What is coming, in order
### Immediate (the next working session)
1. **Phase 7, simulation.** Replace the simulation's arbitrary "forecast noise" setting with values matched to the measured 1-hour and 3-hour accuracy; estimate the demand shape from data where possible; add a sensitivity analysis showing which assumptions matter most. Output stays labelled "assumption-driven".
2. **Housekeeping.** Close GitHub issue #2 (old false alarm).

### Short term (November to December 2026)
3. **~2026-11-10: second freeze (30 days of steady collection, counting from 2026-10-10)** with a new tag (for example `data-freeze-2026-11-09`), then re-run the audit, service-level results, segmentation and forecast. Report what held up and what changed.
4. **Phase 8, dashboard.** Finish the local Shiny app using the findings; it stays local unless you ask for public publishing.
5. **Phase 9, write-up.** Case-study page, README polish, one-page interview script (including the staleness story and why results are modest).
6. **~2026-12-10: third freeze (60 days).** Then watch the Christmas and school-holiday period (exact dates to confirm), which falls in the 60 to 90 day window.

### Medium term (January to April 2027)
7. **~2027-01-09: fourth freeze (90 days).** First look at holiday effects; decide whether weather effects are testable (needs more rain days).
8. **Mid-March 2027:** Fallas festival week (dates to confirm) is a natural test of "event" behaviour.
9. **2027-03-28:** clocks go forward (a skipped local hour). The UTC-hour design and tests already cover this; confirm nothing breaks.
10. **Re-do the XYZ steadiness split** with relative thresholds once there are more weeks (decided in the segmentation findings).

### Long term (through autumn 2027)
11. **Year-over-year view** once a full year exists: seasons, summer vs winter, holidays, rain.
12. **Retrospective:** what changed between the 15-day and the one-year view, as a final portfolio chapter.

## 6. Calendar: what is automatic and what needs you
| When | What | Who |
|---|---|---|
| Every 10 minutes | Collector runs (Cloudflare timer triggers GitHub workflow) | Automatic |
| Daily | Health check; a GitHub issue (and email) opens if collection stalls | Automatic |
| Every push | Tests and CI run | Automatic |
| Occasionally | If you get a health or CI failure email, tell Claude | You |
| **~2027-02-15** | **Renew the GitHub token** used by the timer (it expires **2027-03-01**): make a new token, replace the `GITHUB_TOKEN` secret in the Cloudflare Worker | You (Claude can walk you through) |
| Each freeze date above | Start a session and say "do the 30-day re-run" (or 60/90) | You start, Claude does the work |

## 7. Key decisions and why (full detail in the linked documents)
| Decision | Why | Where |
|---|---|---|
| Treat bike-share as inventory | Direct match to ABC/XYZ, service level, replenishment concepts | README |
| Never report a number that a script did not produce | Credibility; short data history is stated, not hidden | CLAUDE.md |
| Use an outside timer for collection | GitHub's scheduler ran about once per 7 hours | cloudflare/README.md |
| Judge data quality by "count unchanged for N hours" (flag 6 h, exclude 12 h), not `last_reported` | `last_reported` barely moves when counts do | analysis_charter.md |
| Hourly tables keyed on UTC hours | Clock changes cannot merge or invent hours | analysis_charter.md |
| Forecast "any stockout next hour" | A third of stockouts are one snapshot long | analysis_charter.md |
| Freeze datasets with git tags | Results stay reproducible while data keeps growing | dataset_card.md |
| Report uncertainty by resampling days; add a placebo check | Few days, so be modest and check for leaks | forecast_findings.md |

## 8. Known limits and open questions
- **Short history:** one autumn month so far. No season, weather or holiday conclusions. Only 3 light rainy days.
- **No trip data and no truck data:** activity is a lower bound; rebalancing effects cannot be measured, only simulated under stated assumptions.
- **Short stockouts are missed** at 10-minute sampling, so stockout rates are lower bounds.
- **Forecast results come from 9 test days;** intervals are probably too narrow. The model mostly tracks "nearly empty and dropping", not weekly routine.
- **Open:** does `last_reported` refresh in a daily batch (hypothesis, unproven)? Do the early-morning jumps in bike counts reflect truck rebalancing (hypothesis, no truck data)?
- **Dependence on two outside services:** the data provider (outages happen; one so far) and the Cloudflare timer (token expiry 2027-03-01).

## 9. What "done" looks like for the portfolio version (v1)
- [ ] Phase 7 simulation with measured inputs and a sensitivity analysis
- [ ] Phase 8 dashboard finished and tested locally
- [ ] Phase 9 case study, README polish, interview script
- [ ] 30-day re-run completed and compared with the 15-day results
- [ ] You can explain, without notes: what a stockout is here, why `last_reported` was dropped, why the forecast was tested the way it was, and what the results cannot show
A decision for later: whether to publish a public dashboard or page (needs your explicit go-ahead; currently not allowed by the project rules).

## 10. Where things live
| Need | Location |
|---|---|
| Plain-language overview | [README.md](../README.md) |
| Rules for Claude | [CLAUDE.md](../CLAUDE.md) |
| Running log, decisions, blockers | [PROGRESS.md](../PROGRESS.md) |
| Plan and charter | [analysis_plan.md](analysis_plan.md), [analysis_charter.md](analysis_charter.md) |
| Method | [methodology.md](methodology.md) |
| Collector and timer | `src/ingest.py`, `.github/workflows/ingest.yml`, `cloudflare/` |
| SQL models | `dbt/` |
| Audit, analysis, forecast, simulation code | `src/audit/`, `src/analysis/`, `src/forecast/`, `src/simulate/` |
| Figures | `docs/figures/` |
| Frozen data | git tag `data-freeze-2026-10-24` on the `data` branch; local copy `data_frozen/` |

## 11. Quick commands
```bash
git -C data_repo pull                                   # get the latest data
python src/check_data.py data_repo                      # collection health report
pytest -q                                               # all tests
dbt build --project-dir dbt --profiles-dir dbt --vars '{data_root: data_frozen}'   # models on the frozen data
```
