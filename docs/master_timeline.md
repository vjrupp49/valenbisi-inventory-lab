# Master project timeline and outline

The one page to open when you want to know where the project stands. Update it at the end of every phase.
**Last updated: 2026-11-12 (after the second freeze and 33-day re-run).** Repository: https://github.com/vjrupp49/valenbisi-inventory-lab

## 1. The project in one paragraph
Valencia's bike-share system (Valenbisi) treated as an inventory problem: each station is a shelf, bikes are stock,
an empty station is a stockout, a full station is a "blockout" (no free dock), and moving bikes by truck is replenishment.
A GitHub-run collector snapshots the public feed every 10 minutes; SQL models (dbt + DuckDB) turn it into trustworthy
tables; analyses measure service levels, segment stations, forecast stockouts and (next) simulate rebalancing policies.
The goal is a portfolio piece for data, analytics and operations roles, where **honesty about limits matters more than
impressive numbers**.

## 2. Where we are (snapshot, 2026-11-12)
- **Collection:** running automatically since 2026-10-09. The second frozen dataset holds 4,748 snapshots over 34 UTC days (to Nov 11). Four runs failed in the data (a provider outage, HTTP 503, Nov 2 to 3), and a 50-minute GitHub Actions outage on Nov 11 left a gap; collection recovered by itself both times.
- **Analysis:** data audit, descriptive results, station segmentation, a real forecast and a data-based rebalancing simulation are done, each with a written findings document, and all were re-run on the second freeze (33 days).
- **Not yet done:** the 60- and 90-day re-runs, and anything that needs more than one autumn month (seasons, weather, holidays).
- **Quality gates in place:** 50 automated tests, continuous-integration checks on every push (green), a daily health check on collection, a frozen reproducible dataset.

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
| 7 | Rebalancing simulation using measured inputs | Done (first version) | 2026-11-04 | [simulation_findings.md](simulation_findings.md) |
| 8 | Dashboard (local) | Done | 2026-11-04 | `dashboard/app.R` |
| 9 | Write-up and interview story | Done (first version; numbers refreshed 2026-11-12) | 2026-11-05 | [case_study.md](case_study.md), [interview_script.md](interview_script.md) |
| 10 | Keep collecting; re-run at 30, 60, 90 days | **Running** (30-day re-run done 2026-11-12) | next: about 2026-12-10 | [analysis_plan.md](analysis_plan.md), [archive/freeze-2026-10-24/](archive/freeze-2026-10-24/) |

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
| 2026-11-04 | Phase 7: data-based simulation. Two realism fixes along the way (bike conservation; no free rebalancing of displaced bikes). |
| 2026-11-04 to 05 | Phase 8 (local dashboard) and Phase 9 (case study, interview script, README rewritten as a landing page). |
| 2026-11-11 | A 50-minute GitHub Actions outage (4 failed runs, 4 snapshots lost); recovered unaided. |
| 2026-11-12 | Second freeze `data-freeze-2026-11-11` (33 complete days). Whole analysis re-run; 15-day results kept in `docs/archive/freeze-2026-10-24/`. |

## 4. What the project has found so far (all from scripts on the frozen 33-day dataset)
- Stations are empty about 13% of the time and full about 6%; strongly time-of-day dependent; concentrated in a few stations.
- The feed's `last_reported` field is unreliable as a freshness signal, which changed our data-quality method.
- Station activity ranking is very stable; the A/B/C labels are softer; the XYZ steadiness split barely separates stations.
- A forecast of "any stockout next hour" beats simple baselines by about 17% on Brier score, with the advantage fading by 3 hours and gone by 6 (a weekly-pattern average is slightly better at 6 hours).
- In a simulation of the network (assumption-bound; it understates empty stations), forecast-driven rebalancing beats reactive rebalancing by a small amount, and the rebalancing budget matters more than forecast accuracy.
Details and caveats are in the findings documents. Every number must come from a script in this repo.

## 5. What is coming, in order
### Immediate (the next working session)
1. **Done 2026-11-12:** second freeze and full re-run (33 days).
2. **Done 2026-11-05:** GitHub issue #2 (old false alarm) closed.

### Short term (November to December 2026)
3. **Done 2026-11-12: second freeze (tag `data-freeze-2026-11-11`).** Everything re-run; what held and what changed is in each findings document's "What changed with more data" section.
4. **Phase 8, dashboard.** Done 2026-11-04 (local only). Publishing it publicly needs your explicit go-ahead.
5. **Phase 9, write-up.** Done (first version, 2026-11-05); numbers refreshed on 2026-11-12.
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
- **Short history:** one autumn month so far. No season, weather or holiday conclusions. Only light rain (at most 2.3 mm in a reading).
- **No trip data and no truck data:** activity is a lower bound; rebalancing effects cannot be measured, only simulated under stated assumptions.
- **Short stockouts are missed** at 10-minute sampling, so stockout rates are lower bounds.
- **Forecast results come from 27 test days;** intervals are probably too narrow. The model mostly tracks "nearly empty and dropping", not weekly routine.
- **Open:** does `last_reported` refresh in a daily batch (hypothesis, unproven)? Do the early-morning jumps in bike counts reflect truck rebalancing (hypothesis, no truck data)?
- **Dependence on outside services:** the data provider (one outage so far), GitHub Actions (one short outage so far) and the Cloudflare timer (token expiry 2027-03-01).

## 9. What "done" looks like for the portfolio version (v1)
- [x] Phase 7 simulation with measured inputs and a sensitivity analysis (first version)
- [x] Phase 8 dashboard finished and tested locally
- [x] Phase 9 case study, README polish, interview script (first version; refresh numbers after each re-run)
- [x] 30-day re-run completed and compared with the 15-day results
- [ ] You can explain, without notes: what a stockout is here, why `last_reported` was dropped, why the forecast was tested the way it was, and what the results cannot show
A decision for later: whether to publish a public dashboard or page (needs your explicit go-ahead; currently not allowed by the project rules).

## 10. Where things live
| Need | Location |
|---|---|
| Plain-language overview | [README.md](../README.md) |
| Rules for Claude | [CLAUDE.md](../CLAUDE.md) |
| Running log, decisions, blockers | [PROGRESS.md](PROGRESS.md) |
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
