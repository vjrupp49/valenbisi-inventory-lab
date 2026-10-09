"""Monte Carlo simulation of bike-share rebalancing policies. Stations are inventory nodes.

Per hour, per station: pickups ~ Poisson(lam_out), returns ~ Poisson(lam_in). A pickup with no bike is
LOST DEMAND (stockout); a return with no free dock is a LOST RETURN (blockout). Rebalancing rounds at
fixed hours move bikes between stations. Policies:

  none      : no rebalancing (baseline)
  static    : fixed random subset of stations, pushes each toward target fill using current counts only
  reactive  : all stations, current counts only (no look-ahead)
  forecast  : all stations, ranks by projected level at the end of the look-ahead window using a noisy
              forecast of net outflow (noise level is a config assumption)

All policies get the same transfer budget and the same demand draws (common random numbers), so differences
between them come only from the policy. All parameters are in config.toml and are ASSUMPTIONS.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

POLICIES = ("none", "static", "reactive", "forecast")


def load_config(path: str | Path) -> dict:
    with open(path, "rb") as fh:
        return tomllib.load(fh)


@dataclass
class World:
    """One replication's draws: station attributes, expected rates and realised demand."""
    capacity: np.ndarray        # (N,)
    lam_out: np.ndarray         # (T, N) expected pickups per hour
    lam_in: np.ndarray          # (T, N) expected returns per hour
    pickups: np.ndarray         # (T, N) realised
    returns: np.ndarray         # (T, N) realised
    static_route: np.ndarray    # indices of stations on the static route
    init_bikes: np.ndarray


def _pulse(hour: np.ndarray, cfg: dict) -> np.ndarray:
    w = cfg["peak_width_h"]
    return (np.exp(-((hour - cfg["morning_peak_hour"]) ** 2) / (2 * w**2))
            - np.exp(-((hour - cfg["evening_peak_hour"]) ** 2) / (2 * w**2)))


def make_world(cfg: dict, seed: int) -> World:
    rng = np.random.default_rng(seed)
    s, d = cfg["system"], cfg["demand"]
    n, days = s["n_stations"], s["n_days"]
    T = days * 24
    capacity = rng.integers(s["capacity_min"], s["capacity_max"] + 1, n)
    popularity = rng.lognormal(0.0, d["popularity_sigma"], n)
    popularity /= popularity.mean()
    direction = np.clip(rng.normal(0, d["direction_sd"], n), -0.9, 0.9)

    hours = np.arange(24, dtype=float)
    pulse = _pulse(hours, d)                                  # (24,)
    # daily shape: low at night, higher by day (smooth), normalised to mean 1 across the day
    shape = 0.25 + np.clip(np.sin((hours - 5) / 17 * np.pi), 0, None)
    shape /= shape.mean()
    base = d["mean_pickups_per_station_day"] / 24.0

    day_noise = rng.lognormal(0.0, d["day_noise_sigma"], (days, n))
    lam_out = np.empty((T, n))
    lam_in = np.empty((T, n))
    for t in range(T):
        h, day = t % 24, t // 24
        level = base * popularity * shape[h] * day_noise[day]
        skew = d["imbalance_strength"] * direction * pulse[h]
        lam_out[t] = level * np.clip(1 + skew, 0.05, None)
        lam_in[t] = level * np.clip(1 - skew, 0.05, None)
    return World(
        capacity=capacity, lam_out=lam_out, lam_in=lam_in,
        pickups=rng.poisson(lam_out), returns=rng.poisson(lam_in),
        static_route=rng.choice(n, size=min(cfg["rebalancing"]["static_route_stations"], n), replace=False),
        init_bikes=np.round(capacity * s["initial_fill"]).astype(int),
    )


def _transfers(bikes: np.ndarray, capacity: np.ndarray, level: np.ndarray, candidates: np.ndarray,
               budget: int, truck_cap: int, target: np.ndarray) -> int:
    """Greedy: repeatedly move bikes from the station with the largest surplus to the one with the largest
    deficit. `level` is the (projected) bike count used to decide; `bikes` is the real state, modified in place.
    Returns the number of transfers made (each is one pick-up stop plus one drop-off stop)."""
    done = 0
    lvl = level.astype(float).copy()
    for _ in range(budget):
        gap = (target - lvl)[candidates]                      # >0 needs bikes, <0 has surplus
        if gap.size < 2:
            break
        need_i, give_i = candidates[np.argmax(gap)], candidates[np.argmin(gap)]
        if gap.max() <= 0.5 or gap.min() >= -0.5:
            break
        qty = int(min(truck_cap, np.floor(gap.max()), np.floor(-gap.min()),
                      bikes[give_i], capacity[need_i] - bikes[need_i]))
        if qty <= 0:
            break
        bikes[give_i] -= qty
        bikes[need_i] += qty
        lvl[give_i] -= qty
        lvl[need_i] += qty
        done += 1
    return done


def run_policy(world: World, cfg: dict, policy: str, rng_fc: np.random.Generator) -> dict:
    assert policy in POLICIES
    rb, fc = cfg["rebalancing"], cfg["forecast"]
    bikes = world.init_bikes.copy()
    cap = world.capacity
    target = np.round(cap * rb["target_fill"])
    budget = rb["n_trucks"] * rb["transfers_per_truck_per_round"]
    T = world.pickups.shape[0]
    lost_pick = lost_ret = served_pick = served_ret = transfers = 0
    stockout_station_hours = blockout_station_hours = 0
    all_idx = np.arange(cap.size)

    for t in range(T):
        if policy != "none" and (t % 24) in rb["round_hours"]:
            if policy == "static":
                transfers += _transfers(bikes, cap, bikes, world.static_route, budget, rb["truck_capacity"], target)
            elif policy == "reactive":
                transfers += _transfers(bikes, cap, bikes, all_idx, budget, rb["truck_capacity"], target)
            else:  # forecast
                w = slice(t, min(t + rb["lookahead_h"], T))
                net_out = (world.lam_out[w] - world.lam_in[w]).sum(axis=0)
                f_hat = net_out * (1 + rng_fc.normal(0, fc["rel_noise"], cap.size)) + rng_fc.normal(0, fc["abs_noise"], cap.size)
                # plan on the projected level at the end of the window, clipped to feasible range
                projected = np.clip(bikes - f_hat, 0, cap)
                transfers += _transfers(bikes, cap, projected, all_idx, budget, rb["truck_capacity"], target)

        p, r = world.pickups[t], world.returns[t]
        sp = np.minimum(p, bikes)
        bikes = bikes - sp
        free = cap - bikes
        sr = np.minimum(r, free)
        bikes = bikes + sr
        lost_pick += int((p - sp).sum())
        lost_ret += int((r - sr).sum())
        served_pick += int(sp.sum())
        served_ret += int(sr.sum())
        stockout_station_hours += int((bikes == 0).sum())
        blockout_station_hours += int((bikes == cap).sum())

    demand = served_pick + lost_pick
    return {
        "policy": policy,
        "service_level": served_pick / demand if demand else float("nan"),
        "lost_pickups": lost_pick,
        "lost_returns": lost_ret,
        "stockout_station_hours": stockout_station_hours,
        "blockout_station_hours": blockout_station_hours,
        "transfers": transfers,
        "cost": transfers * rb["cost_per_transfer"],
    }


def monte_carlo(cfg: dict, policies=POLICIES) -> list[dict]:
    """Run n_replications worlds; every policy sees the same world (common random numbers)."""
    mc = cfg["monte_carlo"]
    rows = []
    for rep in range(mc["n_replications"]):
        world = make_world(cfg, mc["seed"] + rep)
        for pol in policies:
            res = run_policy(world, cfg, pol, np.random.default_rng(10_000 + mc["seed"] + rep))
            res["rep"] = rep
            rows.append(res)
    return rows
