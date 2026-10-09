"""Probabilistic forecast scoring: Brier score, skill vs. a base-rate forecast, calibration table."""
from __future__ import annotations

import numpy as np
import pandas as pd


def brier(y_true, p) -> float:
    y, p = np.asarray(y_true, float), np.asarray(p, float)
    return float(np.mean((p - y) ** 2))


def brier_skill(y_true, p, p_ref) -> float:
    """1 - BS/BS_ref. Positive = better than the reference forecast, 0 = same, negative = worse."""
    ref = brier(y_true, p_ref)
    return float("nan") if ref == 0 else 1.0 - brier(y_true, p) / ref


def calibration_table(y_true, p, n_bins: int = 10) -> pd.DataFrame:
    """Equal-width probability bins: mean predicted vs observed frequency. A calibrated model has them equal."""
    df = pd.DataFrame({"y": np.asarray(y_true, float), "p": np.asarray(p, float)})
    df["bin"] = np.minimum((df["p"] * n_bins).astype(int), n_bins - 1)
    g = df.groupby("bin").agg(n=("y", "size"), mean_pred=("p", "mean"), obs_rate=("y", "mean")).reset_index()
    g["abs_gap"] = (g["mean_pred"] - g["obs_rate"]).abs()
    return g


def expected_calibration_error(y_true, p, n_bins: int = 10) -> float:
    t = calibration_table(y_true, p, n_bins)
    return float((t["n"] * t["abs_gap"]).sum() / t["n"].sum())
