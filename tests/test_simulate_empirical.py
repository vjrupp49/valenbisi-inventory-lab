"""Data-based simulation: estimation, bike conservation, calibration and bookkeeping (hand-made / SYNTHETIC data)."""
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from simulate import empirical as E  # noqa: E402
from simulate.engine import load_config, returns_at  # noqa: E402
from test_dbt_models import build_dbt, hand_made, pytestmark  # noqa: E402,F401  (pytestmark skips if dbt is missing)

CFG = load_config(ROOT / "src" / "simulate" / "config.toml")
CFG["system"]["n_days"] = 3


def toy_params(n=40, seed=0, dispersion=0.0) -> E.Params:
    rng = np.random.default_rng(seed)
    cap = rng.integers(15, 30, n).astype(float)
    pop = rng.lognormal(0, 0.5, n)
    pop /= pop.mean()
    hours = np.arange(24)
    shape = (0.3 + np.clip(np.sin((hours - 5) / 17 * np.pi), 0, None))[:, None]
    direction = rng.normal(0, 0.4, n)[None, :]
    pulse = (np.exp(-((hours - 8.5) ** 2) / 4) - np.exp(-((hours - 18.5) ** 2) / 4))[:, None]
    base = 2.0 * shape * pop[None, :]
    return E.Params([str(i) for i in range(n)], cap, np.round(cap * 0.4), base * (1 + 0.6 * direction * pulse), base * (1 - 0.6 * direction * pulse),
                    0.2, 0.1, {}, dispersion, 0.3)


def test_estimate_recovers_known_rates_and_ignores_trucks_and_stuck(tmp_path):
    # Local midnight in January is 23:00 UTC. Three complete days of 10-minute snapshots.
    start = datetime(2030, 1, 6, 23, 0, tzinfo=timezone.utc)
    n = 144 * 3
    alt = [5 if k % 2 == 0 else 4 for k in range(n)]           # one pickup and one return every 20 minutes -> 3 per hour each
    with_trucks = list(alt)
    for k in (50, 194, 338):                                    # a +10 jump then back: truck-like moves (>= 8 bikes)
        with_trucks[k] = alt[k] + 10
    series = {"A": alt, "C": with_trucks, "B": [5] * n}         # B never changes -> stuck, too little usable exposure
    status, meta, info = hand_made(series, start, capacity=30)
    build_dbt(tmp_path, status, meta, info)
    p = E.estimate(tmp_path / "t.duckdb", min_exposure_h=20)  # only 3 days of toy data
    assert set(p.station_ids) == {"A", "C"} and p.summary["n_stations_excluded_low_exposure"] == 1
    ia, ic = p.station_ids.index("A"), p.station_ids.index("C")
    assert p.base_out[:, ia] == pytest.approx(np.full(24, 3.0), rel=0.10)   # hour 0 has one fewer interval in toy data
    assert p.base_in[:, ia] == pytest.approx(np.full(24, 3.0), rel=0.10)
    assert p.base_out[:, ic].mean() == pytest.approx(3.0, rel=0.06)       # jumps removed from the rates (small exposure effect only)
    assert p.summary["jumps_up_per_day"] == pytest.approx(1.0, abs=0.01) and p.summary["jumps_down_per_day"] == pytest.approx(1.0, abs=0.01)
    assert p.trip_hours == pytest.approx(0.05)                             # flat station level -> shortest allowed trip time


def test_world_is_reproducible_and_expected_pickups_match_rates():
    p = toy_params()
    w1, w2 = E.make_world(p, CFG, 5), E.make_world(p, CFG, 5)
    assert (w1.pickups == w2.pickups).all() and (w1.u_ret == w2.u_ret).all()
    assert not (E.make_world(p, CFG, 6).pickups == w1.pickups).all()
    big = [E.make_world(p, CFG, s).lam_out.mean() for s in range(40)]
    assert np.mean(big) == pytest.approx(p.base_out.mean(), rel=0.1)       # day multipliers have mean 1


def test_returns_follow_served_pickups():
    p = toy_params()
    w = E.make_world(p, CFG, 1)
    w.u_ret = np.random.default_rng(0).random(w.u_ret.shape)
    tot = [returns_at(w, 10, 100.0, 50.0, 10.0).sum() for _ in range(1)]
    mu = w.trip_same_hour * 50.0 + (1 - w.trip_same_hour) * 100.0 + 10.0
    draws = []
    for s in range(300):
        w.u_ret = np.random.default_rng(s).random(w.u_ret.shape)
        draws.append(returns_at(w, 10, 100.0, 50.0, 10.0).sum())
    assert np.mean(draws) == pytest.approx(mu, rel=0.05) and tot[0] >= 0


def test_fleet_is_conserved_without_rebalancing():
    p = toy_params()
    w = E.make_world(p, CFG, 3)
    before, after = E.trajectory_none(w)
    start = after[0].sum()
    # bikes at stations may dip (bikes in use) but must not drift away
    assert after[-1].sum() == pytest.approx(start, rel=0.2) and after.sum(axis=1).min() > 0.6 * start


def test_calibration_hits_a_reachable_target_and_flags_unreachable_ones():
    p = toy_params(n=60)
    a = E.stockout_scores(p, CFG, 3, (0, 12), reps=6, seed=1)
    assert a[0] > a[12]                                                    # more forecast noise -> worse ranking
    target = (a[0] + a[12]) / 2
    cal = E.calibrate_noise(p, CFG, {3: target}, grid=(0, 2, 4, 8, 12), reps=6, seed=1)[3]
    assert 0 < cal["noise_sd_bikes"] < 12 and cal["note"] == ""
    cal2 = E.calibrate_noise(p, CFG, {3: 0.999}, grid=(0, 4), reps=4, seed=1)[3]
    assert cal2["noise_sd_bikes"] == 0.0 and "not reachable" in cal2["note"]


def test_scenarios_are_reproducible_and_paired_differences_add_up():
    p = toy_params(n=30)
    specs = E.policy_specs({3: {"noise_sd_bikes": 2.0}})
    d1 = E.run_scenario(p, CFG, specs, reps=3, seed=9)
    d2 = E.run_scenario(p, CFG, specs, reps=3, seed=9)
    pd.testing.assert_frame_equal(d1, d2)
    assert set(d1["name"]) == {"none", "static", "reactive", "forecast_3h", "oracle_3h"}
    m, lo, hi = E.paired_difference(d1, "reactive", "none")
    direct = d1[d1["name"] == "none"]["lost_pickups_per_day"].mean() - d1[d1["name"] == "reactive"]["lost_pickups_per_day"].mean()
    assert m == pytest.approx(direct) and lo <= m <= hi
    assert (d1[d1["name"] == "none"]["transfers"] == 0).all()
    # a bigger budget can only move more bikes
    big = E.run_scenario(p, CFG, specs[:3], reps=3, seed=9, transfers_per_round=12)
    assert big[big["name"] == "reactive"]["transfers"].mean() >= d1[d1["name"] == "reactive"]["transfers"].mean()


def test_measured_aucs_are_read_from_the_forecast_results_files(tmp_path):
    for h, auc in ((1, 0.93), (3, 0.81), (6, 0.71)):
        name = {1: "forecast_results.md", 3: "forecast_results_h3.md", 6: "forecast_results_h6.md"}[h]
        (tmp_path / name).write_text(
            "| model | base_rate | brier | brier_lo | brier_hi | auc | log_loss | ece |\n|---|---|---|---|---|---|---|---|\n"
            f"| persistence | 0.2 | 0.1 | 0.1 | 0.1 | 0.5 | 0.4 | 0.1 |\n| gbm | 0.2 | 0.08 | 0.07 | 0.09 | {auc} | 0.2 | 0.01 |\n", encoding="utf-8")
    assert E.measured_aucs(tmp_path) == {1: 0.93, 3: 0.81, 6: 0.71}
