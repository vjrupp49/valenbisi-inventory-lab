# Dataset card: frozen dataset `data-freeze-2026-10-24`

Purpose: a fixed copy of the collected data, so every result in this project can be re-created exactly,
even though collection keeps running and the live `data` branch keeps growing.

| Item | Value |
|---|---|
| Git tag (on the `data` branch) | `data-freeze-2026-10-24` |
| Commit | `07374474a378d98f615c302dc51a87150732a8fa` (message: `data: 2026-10-24T23:50Z`) |
| Contents | every snapshot taken from 2026-10-09 05:58 UTC through 2026-10-24 23:50 UTC |
| Snapshots / station rows / stations | 2,168 / 599,742 / 277 (from audit check A1) |
| Why this cutoff | ends on a whole UTC day, and stops before Spain's clock change on 2026-10-25 |
| Full days | 15 complete UTC days (Oct 10 to Oct 24); Oct 9 is partial and was collected before the reliable timer |
| Collection continues? | Yes. Nothing here stops or changes the collector. The freeze is only a labelled copy. |

## Recreate it
```bash
git -C data_repo fetch --tags
git -C data_repo worktree add ../data_frozen data-freeze-2026-10-24
```
`data_frozen/` is ignored by git (it is data, not source). Run the audit or models against it with `--data data_frozen`
(audit) or `--vars '{data_root: data_frozen}'` (dbt).

## Sources and licences
- Valenbisi GBFS v3 feeds via the JCDecaux Open Licence (station status and station information).
- Open-Meteo current weather for Valencia, CC BY 4.0.

## Tables
| Table | Grain | Notes |
|---|---|---|
| `station_status/` | station x snapshot | bike and dock counts, disabled counts, flags, `last_reported` |
| `run_meta/` | collector run | success, feed age, weather |
| `station_information/` | station x day | name, location, capacity |

## Known problems in this dataset
See [data_integrity_report.md](data_integrity_report.md). The most important: `last_reported` is not a usable
freshness signal, and the period is only about two weeks of one autumn month.

## Later datasets
New freezes get their own tag (for example `data-freeze-2026-11-24`). Never move or reuse an existing tag.
