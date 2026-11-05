# Reproducing the results

Requires Python 3.11+. R (with ggplot2, dplyr, scales, shiny) is only needed for the figures and the dashboard.

```bash
python -m venv .venv && source .venv/bin/activate        # Windows: .venv/Scripts/activate
pip install -r requirements.txt -r requirements-dbt.txt
pytest -q
```

## Get the data
Collected snapshots live on the `data` branch, kept separate so `main` stays clean:

```bash
git clone --branch data --single-branch https://github.com/vjrupp49/valenbisi-inventory-lab data_repo
python src/check_data.py data_repo     # health report: gaps, errors, feed freshness
```
The results in this repo come from a frozen copy of that data, the git tag `data-freeze-2026-10-24` (see [dataset_card.md](dataset_card.md)).
On Windows consoles set `PYTHONUTF8=1` before running `src/check_data.py`.

## Model the data
```bash
dbt build --project-dir dbt --profiles-dir dbt --vars '{data_root: dbt/sample_data}'   # SYNTHETIC sample (what CI runs)
dbt build --project-dir dbt --profiles-dir dbt                                          # real data in data_repo/
```

## Re-create each result (on the frozen dataset)
```bash
python src/audit/run_audit.py --data data_frozen --out docs/data_integrity_results.md --dbt-db dbt/target/valenbisi.duckdb
python src/analysis/service_level.py --db dbt/target/valenbisi.duckdb --out docs/service_level_results.md
python src/analysis/segmentation_stability.py --db dbt/target/valenbisi.duckdb --out docs/segmentation_results.md
python src/forecast/evaluate.py --db dbt/target/valenbisi.duckdb --out docs/forecast_results.md      # add --horizon 3 / --horizon 6 and --out docs/forecast_results_h3.md / _h6.md
python src/simulate/run_empirical.py --db dbt/target/valenbisi.duckdb --out docs/simulation_results.md   # ~2.5 minutes
Rscript analysis/plot_service_level.R
Rscript analysis/plot_model_results.R
```

## Synthetic-data development
```bash
python src/forecast/run.py --db dbt/target/valenbisi.duckdb --synthetic
python src/simulate/run.py                                  # fully synthetic simulation
```

## Dashboard (local)
```bash
python src/export_marts.py --db dbt/target/valenbisi.duckdb --out dashboard/data
Rscript -e 'shiny::runApp("dashboard")'
```
