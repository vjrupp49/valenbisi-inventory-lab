"""Forecast scaffold tests. All data here is SYNTHETIC or hand-made; no real-data claims."""
import numpy as np
import pandas as pd
import pytest

from forecast.backtest import rolling_origin, summarize
from forecast.features import FEATURES, TARGET, build_dataset
from forecast.metrics import brier, brier_skill, calibration_table, expected_calibration_error
from forecast.models import GradientBoosting, HourOfWeek, Persistence


def _hourly(n_days=6, stations=("a", "b"), seed=0):
    """Hand-made hourly frame: station 'a' is out of bikes every day 8-9h, 'b' never."""
    rng = np.random.default_rng(seed)
    rows = []
    for s in stations:
        for h in range(n_days * 24):
            t = pd.Timestamp("2030-01-07") + pd.Timedelta(hours=h)
            so = (s == "a") and t.hour in (8, 9)
            rows.append({
                "station_id": s, "local_hour": t, "local_date": t.date(), "hour_of_day": t.hour,
                "day_of_week": t.isoweekday(), "avg_availability": 0.0 if so else 0.5 + rng.normal(0, .02),
                "min_bikes": 0 if so else 8, "stockout_share": float(so), "stale_share": 0.0,
                "any_stockout": so,
            })
    return pd.DataFrame(rows)


def test_metrics_basic():
    assert brier([1, 0], [1, 0]) == 0
    assert brier([1, 0], [0.5, 0.5]) == pytest.approx(0.25)
    assert brier_skill([1, 0], [1, 0], [0.5, 0.5]) == pytest.approx(1.0)
    assert expected_calibration_error([1, 1, 0, 0], [0.5] * 4) == pytest.approx(0.0)
    t = calibration_table([1, 0, 1, 1], [0.9, 0.1, 0.8, 0.95], n_bins=5)
    assert t["n"].sum() == 4


def test_target_is_next_hour_stockout():
    ds = build_dataset(_hourly(), horizon_h=1)
    row = ds[(ds["station_id"] == "a") & (ds["local_hour"] == pd.Timestamp("2030-01-08 07:00"))].iloc[0]
    assert row[TARGET] == 1  # the 08:00 hour is a stockout
    row = ds[(ds["station_id"] == "a") & (ds["local_hour"] == pd.Timestamp("2030-01-08 10:00"))].iloc[0]
    assert row[TARGET] == 0


def test_no_feature_leakage_from_future():
    """Changing the future (t+1 and later) must not change any feature at t."""
    h = _hourly()
    base = build_dataset(h)
    h2 = h.copy()
    t0 = pd.Timestamp("2030-01-09 12:00")
    future = h2["local_hour"] > t0
    h2.loc[future, ["avg_availability", "stockout_share", "min_bikes"]] = [0.123, 1.0, 0]
    h2.loc[future, "any_stockout"] = True
    alt = build_dataset(h2)
    k = ["station_id", "local_hour"]
    a = base[base["local_hour"] <= t0].set_index(k)[FEATURES]
    b = alt[alt["local_hour"] <= t0].set_index(k)[FEATURES]
    pd.testing.assert_frame_equal(a.sort_index(), b.sort_index())


def test_gap_gives_missing_lag_not_shifted_lag():
    h = _hourly()
    gone = (h["station_id"] == "a") & (h["local_hour"] == pd.Timestamp("2030-01-08 05:00"))
    ds = build_dataset(h[~gone])
    row = ds[(ds["station_id"] == "a") & (ds["local_hour"] == pd.Timestamp("2030-01-08 06:00"))].iloc[0]
    assert np.isnan(row["avail_lag1"])


def test_models_learn_the_daily_pattern():
    ds = build_dataset(_hourly())
    train = ds[ds["date"] < pd.Timestamp("2030-01-11")]
    test = ds[ds["date"] >= pd.Timestamp("2030-01-11")]
    for m in (HourOfWeek(), GradientBoosting()):
        p = m.fit(train).predict_proba(test)
        assert brier(test[TARGET], p) < 0.05, m.name
    # persistence is wrong right at the pattern edges, so it should be worse than hour-of-week here
    p_per = Persistence().fit(train).predict_proba(test)
    p_how = HourOfWeek().fit(train).predict_proba(test)
    assert brier(test[TARGET], p_per) > brier(test[TARGET], p_how)


def test_rolling_origin_never_trains_on_test_day():
    ds = build_dataset(_hourly())
    seen = []

    class Spy(Persistence):
        name = "spy"

        def fit(self, train):
            seen.append(train["local_hour"].max())
            return self

    preds = rolling_origin(ds, horizon_h=1, min_train_days=2, models=[Spy()])
    for fold_day, max_train in zip(sorted(preds["fold_date"].unique()), seen):
        assert max_train + pd.Timedelta(hours=1) < pd.Timestamp(fold_day)
    assert not summarize(preds, ref_model="spy").empty


def test_real_data_guard_refuses_few_days(tmp_path, capsys):
    import duckdb

    from forecast import run

    db = tmp_path / "x.duckdb"
    con = duckdb.connect(str(db))
    con.register("h", _hourly(n_days=3))
    con.sql("create table fct_station_hour as select *, true as is_service_eligible from h")
    con.close()
    assert run.main(["--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert "Not reporting model results" in out and "brier" not in out
