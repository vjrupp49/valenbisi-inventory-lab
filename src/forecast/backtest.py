"""Rolling-origin (expanding window) backtest.

For each test day D (after `min_train_days` days of history): fit on all rows whose TARGET hour
is strictly before D's first hour, then predict every origin hour on D. The training cut accounts
for the horizon so no training label peeks into the test day.
"""
from __future__ import annotations

import pandas as pd

from .features import TARGET
from .metrics import brier, brier_skill, expected_calibration_error
from .models import all_models


def rolling_origin(ds: pd.DataFrame, horizon_h: int = 1, min_train_days: int = 2, seed: int = 0,
                   models=None) -> pd.DataFrame:
    """Return one row per (test row, model): station_id, local_hour, y, model, p, fold_date."""
    days = sorted(ds["date"].unique())
    preds = []
    for d in days[min_train_days:]:
        day_start = pd.Timestamp(d)
        day_end = day_start + pd.Timedelta(days=1)
        # label for origin t lives at t + horizon, so require t + horizon < day_start
        train = ds[ds["local_hour"] + pd.Timedelta(hours=horizon_h) < day_start]
        test = ds[(ds["local_hour"] >= day_start) & (ds["local_hour"] < day_end)]
        if train.empty or test.empty:
            continue
        for m in (models or all_models(seed)):
            m.fit(train)  # fit() resets all state, so reusing the instance across folds is safe
            p = m.predict_proba(test)
            out = test[["station_id", "local_hour", TARGET]].copy()
            out["model"] = m.name
            out["p"] = p
            out["fold_date"] = day_start
            preds.append(out)
    return pd.concat(preds, ignore_index=True) if preds else pd.DataFrame()


def summarize(preds: pd.DataFrame, ref_model: str = "hour_of_week") -> pd.DataFrame:
    """Per-model Brier, skill vs `ref_model`, calibration error, base rate and n."""
    if preds.empty:
        return pd.DataFrame()
    ref = preds[preds["model"] == ref_model].set_index(["station_id", "local_hour"])["p"]
    rows = []
    for name, g in preds.groupby("model"):
        g = g.set_index(["station_id", "local_hour"])
        p_ref = ref.reindex(g.index).to_numpy()
        rows.append({
            "model": name, "n": len(g), "base_rate": g[TARGET].mean(),
            "brier": brier(g[TARGET], g["p"]),
            f"skill_vs_{ref_model}": brier_skill(g[TARGET], g["p"], p_ref),
            "ece": expected_calibration_error(g[TARGET], g["p"]),
        })
    return pd.DataFrame(rows).sort_values("brier").reset_index(drop=True)
