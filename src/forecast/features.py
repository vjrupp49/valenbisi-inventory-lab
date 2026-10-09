"""Build the supervised dataset: predict whether a station has a stockout in a future hour.

Input is the station x hour table (dbt model `fct_station_hour`, or any frame with the same columns).
One row = (station, hour t). Target = any_stockout at hour t + horizon. Every feature uses only
information available at hour t or earlier (no leakage); lagged values are looked up by exact hour,
so a gap in collection produces a missing feature, not a silently shifted one.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FEATURES = [
    "hour_of_day", "day_of_week", "avg_availability", "min_bikes", "stockout_share", "stale_share",
    "avail_lag1", "avail_lag2", "avail_lag3", "avail_change_1h", "stockout_lag1",
]
TARGET = "y"


def load_hourly(db_path: str) -> pd.DataFrame:
    """Read fct_station_hour (service-eligible stations only) from a dbt-built DuckDB file."""
    import duckdb

    con = duckdb.connect(db_path, read_only=True)
    try:
        return con.sql(
            "select station_id, local_hour, local_date, hour_of_day, day_of_week, avg_availability, "
            "min_bikes, stockout_share, stale_share, any_stockout from fct_station_hour "
            "where is_service_eligible"
        ).df()
    finally:
        con.close()


def build_dataset(hourly: pd.DataFrame, horizon_h: int = 1) -> pd.DataFrame:
    """Return rows with FEATURES, TARGET and `local_hour` (the origin hour t). Rows with no target are dropped."""
    df = hourly.copy()
    df["local_hour"] = pd.to_datetime(df["local_hour"])
    df["any_stockout"] = df["any_stockout"].astype(float)
    key = ["station_id", "local_hour"]

    def shifted(col: str, hours: int, name: str) -> pd.DataFrame:
        # value of `col` at (t - hours), re-keyed to t
        s = df[key + [col]].copy()
        s["local_hour"] = s["local_hour"] + pd.Timedelta(hours=hours)
        return s.rename(columns={col: name})

    out = df
    for lag in (1, 2, 3):
        out = out.merge(shifted("avg_availability", lag, f"avail_lag{lag}"), on=key, how="left")
    out = out.merge(shifted("any_stockout", 1, "stockout_lag1"), on=key, how="left")
    out["avail_change_1h"] = out["avg_availability"] - out["avail_lag1"]

    # target: stockout at t + horizon  ==  value at (t + h) re-keyed to t, i.e. shift by -h
    tgt = shifted("any_stockout", -horizon_h, TARGET)
    out = out.merge(tgt, on=key, how="inner").dropna(subset=[TARGET])
    out[TARGET] = out[TARGET].astype(int)
    out["date"] = out["local_hour"].dt.normalize()
    out["how"] = out["day_of_week"] * 24 + out["hour_of_day"]  # hour-of-week index
    return out.sort_values(key).reset_index(drop=True)


def n_days(hourly: pd.DataFrame) -> int:
    return int(pd.to_datetime(hourly["local_hour"]).dt.normalize().nunique())


def fillna_for_model(x: pd.DataFrame) -> pd.DataFrame:
    """Tree models in sklearn's HistGradientBoosting handle NaN natively; this just enforces float dtype."""
    return x[FEATURES].astype(float).replace([np.inf, -np.inf], np.nan)
