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


def auc(y_true, p) -> float:
    """Area under the ROC curve (ranking quality, ignores calibration). NaN if only one class is present."""
    from sklearn.metrics import roc_auc_score

    y = np.asarray(y_true)
    return float("nan") if len(np.unique(y)) < 2 else float(roc_auc_score(y, p))


def log_loss(y_true, p) -> float:
    y, p = np.asarray(y_true, float), np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
