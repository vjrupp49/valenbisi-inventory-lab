"""Simulation invariants. Parameters come from config.toml, which is assumption-only."""
from pathlib import Path

import numpy as np

from simulate.engine import _transfers, load_config, make_world, monte_carlo, run_policy

CFG_PATH = Path(__file__).resolve().parents[1] / "src" / "simulate" / "config.toml"


def small_cfg(reps=6):
    cfg = load_config(CFG_PATH)
    cfg["monte_carlo"]["n_replications"] = reps
    cfg["system"]["n_days"] = 2
    cfg["system"]["n_stations"] = 20
    cfg["rebalancing"]["static_route_stations"] = 8
    return cfg


def test_transfers_conserve_bikes_and_respect_capacity():
    cap = np.array([10, 10, 10, 10])
    bikes = np.array([10, 0, 5, 9])
    total = bikes.sum()
    n = _transfers(bikes, cap, bikes, np.arange(4), budget=5, truck_cap=3, target=np.array([5, 5, 5, 5]))
    assert bikes.sum() == total
    assert (bikes >= 0).all() and (bikes <= cap).all()
    assert 1 <= n <= 5


def test_transfer_budget_is_respected():
    cfg = small_cfg()
    budget = cfg["rebalancing"]["n_trucks"] * cfg["rebalancing"]["transfers_per_truck_per_round"]
    rounds = len(cfg["rebalancing"]["round_hours"]) * cfg["system"]["n_days"]
    world = make_world(cfg, 1)
    for pol in ("static", "reactive", "forecast"):
        res = run_policy(world, cfg, pol, np.random.default_rng(0))
        assert res["transfers"] <= budget * rounds


def test_none_policy_makes_no_transfers_and_accounts_all_demand():
    cfg = small_cfg()
    world = make_world(cfg, 3)
    res = run_policy(world, cfg, "none", np.random.default_rng(0))
    assert res["transfers"] == 0
    served = res["service_level"] * (world.pickups.sum())
    assert abs(served - (world.pickups.sum() - res["lost_pickups"])) < 1e-6


def test_deterministic_for_seed():
    cfg = small_cfg()
    assert monte_carlo(cfg) == monte_carlo(cfg)


def test_perfect_forecast_not_worse_than_no_rebalancing_on_average():
    cfg = small_cfg(reps=20)
    cfg["forecast"]["rel_noise"] = 0.0
    cfg["forecast"]["abs_noise"] = 0.0
    rows = monte_carlo(cfg, policies=("none", "forecast"))
    none = np.mean([r["lost_pickups"] for r in rows if r["policy"] == "none"])
    fc = np.mean([r["lost_pickups"] for r in rows if r["policy"] == "forecast"])
    assert fc <= none


def test_common_random_numbers_same_demand_for_all_policies():
    cfg = small_cfg()
    w1, w2 = make_world(cfg, 5), make_world(cfg, 5)
    assert (w1.pickups == w2.pickups).all() and (w1.returns == w2.returns).all()
