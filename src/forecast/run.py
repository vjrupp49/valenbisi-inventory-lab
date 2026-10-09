"""Run the rolling-origin backtest from a dbt-built DuckDB file.

    python src/forecast/run.py --db dbt/target/valenbisi.duckdb --synthetic     # development, labelled SYNTHETIC
    python src/forecast/run.py --db dbt/target/valenbisi.duckdb                 # real data (guarded)

Guard: for real data this refuses to print any score until MIN_REAL_DAYS days exist (project rule:
no real model results before 14 days of real data).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from forecast.backtest import rolling_origin, summarize  # noqa: E402
from forecast.features import build_dataset, load_hourly, n_days  # noqa: E402
from forecast.metrics import calibration_table  # noqa: E402

MIN_REAL_DAYS = 14


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--db", required=True)
    ap.add_argument("--synthetic", action="store_true", help="the DB was built from src/synth.py data")
    ap.add_argument("--horizon", type=int, default=1, help="hours ahead")
    ap.add_argument("--min-train-days", type=int, default=2)
    a = ap.parse_args(argv)

    hourly = load_hourly(a.db)
    days = n_days(hourly)
    if not a.synthetic and days < MIN_REAL_DAYS:
        print(f"Only {days} distinct day(s) of real data; need {MIN_REAL_DAYS}. "
              "Not reporting model results (by design).")
        return 0

    ds = build_dataset(hourly, a.horizon)
    preds = rolling_origin(ds, a.horizon, a.min_train_days)
    if preds.empty:
        print("Not enough days for a backtest fold.")
        return 0
    label = "SYNTHETIC DATA - NOT A REAL RESULT" if a.synthetic else f"real data, {days} days"
    print(f"== Backtest ({label}); horizon {a.horizon} h; {days} days ==")
    print(summarize(preds).to_string(index=False))
    best = summarize(preds).iloc[0]["model"]
    print(f"\nCalibration of '{best}':")
    print(calibration_table(preds[preds['model'] == best]['y'], preds[preds['model'] == best]['p']).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
