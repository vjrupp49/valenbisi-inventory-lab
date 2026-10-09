"""Forecasters. Each has fit(train_df) and predict_proba(test_df) -> P(stockout at t + horizon).

Baselines come first on purpose: a model only counts if it beats them out of sample.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from .features import FEATURES, TARGET, fillna_for_model

EPS = 0.02  # keep probabilities away from 0/1 so a single miss is not infinitely punished


class Persistence:
    """P(stockout next hour) = whether the station had a stockout this hour (clipped)."""

    name = "persistence"

    def fit(self, train: pd.DataFrame):
        return self

    def predict_proba(self, test: pd.DataFrame) -> np.ndarray:
        cur = test["stockout_share"].fillna(0.0).to_numpy()
        return np.clip((cur > 0).astype(float), EPS, 1 - EPS)


class HourOfWeek:
    """Station x hour-of-week mean of the target in the training window, with shrinkage fallbacks.

    Falls back to the station x hour-of-day mean, then the station mean, then the global mean when a
    cell has too few observations (shrinks toward the coarser level with weight k).
    """

    name = "hour_of_week"

    def __init__(self, k: float = 3.0):
        self.k = k

    def fit(self, train: pd.DataFrame):
        self.global_ = float(train[TARGET].mean())
        st = train.groupby("station_id")[TARGET].agg(["sum", "count"])
        self.station_ = ((st["sum"] + self.k * self.global_) / (st["count"] + self.k)).to_dict()
        hod = train.groupby(["station_id", "hour_of_day"])[TARGET].agg(["sum", "count"])
        self.hod_ = {}
        for (sid, h), r in hod.iterrows():
            prior = self.station_.get(sid, self.global_)
            self.hod_[(sid, h)] = (r["sum"] + self.k * prior) / (r["count"] + self.k)
        how = train.groupby(["station_id", "how"])[TARGET].agg(["sum", "count"])
        self.how_ = {}
        for (sid, w), r in how.iterrows():
            prior = self.hod_.get((sid, w % 24), self.station_.get(sid, self.global_))
            self.how_[(sid, w)] = (r["sum"] + self.k * prior) / (r["count"] + self.k)
        return self

    def predict_proba(self, test: pd.DataFrame) -> np.ndarray:
        out = []
        for sid, h, w in zip(test["station_id"], test["hour_of_day"], test["how"]):
            p = self.how_.get((sid, w))
            if p is None:
                p = self.hod_.get((sid, h), self.station_.get(sid, self.global_))
            out.append(p)
        return np.clip(np.array(out, dtype=float), EPS, 1 - EPS)


class GradientBoosting:
    """Gradient-boosted trees (sklearn HistGradientBoostingClassifier) on the lagged features."""

    name = "gbm"

    def __init__(self, seed: int = 0, **kw):
        params = dict(max_depth=4, learning_rate=0.08, max_iter=150, min_samples_leaf=20, random_state=seed)
        params.update(kw)
        self.params = params

    def fit(self, train: pd.DataFrame):
        y = train[TARGET].to_numpy()
        self.constant_ = float(y.mean()) if len(np.unique(y)) < 2 else None
        if self.constant_ is None:
            self.model_ = HistGradientBoostingClassifier(**self.params).fit(fillna_for_model(train), y)
        return self

    def predict_proba(self, test: pd.DataFrame) -> np.ndarray:
        if self.constant_ is not None:
            p = np.full(len(test), self.constant_)
        else:
            p = self.model_.predict_proba(fillna_for_model(test))[:, 1]
        return np.clip(p, EPS / 4, 1 - EPS / 4)


def all_models(seed: int = 0):
    return [Persistence(), HourOfWeek(), GradientBoosting(seed=seed)]


__all__ = ["Persistence", "HourOfWeek", "GradientBoosting", "all_models", "FEATURES"]
