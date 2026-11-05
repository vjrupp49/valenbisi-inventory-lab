"""Data-based rebalancing simulation (Phase 7).

What is estimated from the frozen dataset, and what stays an assumption:

  ESTIMATED FROM DATA          the real stations and their capacities; the opening bike level of each station;
                               pickup and return rates per station and Madrid hour (inferred from bike-count changes);
                               day-to-day variation (city-wide and per station); forecast accuracy (matched to the
                               measured AUC in docs/forecast_results*.md).
  ASSUMPTIONS (config.toml)    the rebalancing budget (trucks, transfers per round, round hours), the target fill,
                               the demand scale (true demand is higher than counted), who the static route visits.

Known biases of the demand estimate, handled or flagged:
  * Counted pickups are a LOWER BOUND on true trips (out-and-back within one 10-minute step is invisible), so the
    demand scale is a sensitivity parameter, not a fact.
  * A station cannot lend a bike it does not have. Rates are therefore computed only over intervals that STARTED with
    a bike available (pickups) or a free dock (returns), which removes most of the censoring from empty/full stations.
  * Jumps of JUMP bikes or more in one step are treated as truck moves, not trips, and left out of the rates.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from .engine import POLICIES, World, returns_at, run_policy

JUMP = 8                    # bike-count change in one step treated as a truck move
MIN_SNAPSHOTS_PER_DAY = 138
MIN_EXPOSURE_H = 100        # a station needs this many hours of usable intervals to be simulated
SHRINK_K_H = 3.0            # pseudo-exposure (hours) pulling station-hour rates toward the station's own average profile


@dataclass
class Params:
    station_ids: list
    capacity: np.ndarray        # (N,)
    init_bikes: np.ndarray      # (N,)
    base_out: np.ndarray        # (24, N) pickups per hour, counted
    base_in: np.ndarray         # (24, N) returns per hour, counted
    sigma_city: float
    sigma_station: float
    summary: dict
    dispersion: float = 0.0     # extra-Poisson variation of hourly counts (gamma mixing); 0 = plain Poisson
    trip_hours: float = 0.3     # average time a bike spends in use (hours), from Little's law on the daily dip in station levels


# ----------------------------------------------------------------------------- estimation
def estimate(db: Path, jump: int = JUMP, min_exposure_h: float = MIN_EXPOSURE_H) -> Params:
    con = duckdb.connect(str(db), read_only=True)
    con.execute("SET TimeZone='UTC'")
    con.execute(
        f"CREATE TEMP TABLE days AS SELECT local_date FROM fct_station_snapshot GROUP BY 1 "
        f"HAVING count(DISTINCT snapshot_ts) >= {MIN_SNAPSHOTS_PER_DAY}"
    )
    agg = con.execute(
        f"""
        WITH x AS (
            SELECT station_id, snapshot_ts, hour_of_day, local_date, bikes, docks, is_installed, is_renting, is_returning,
                   is_stuck_excluded, bikes_delta,
                   lag(docks) OVER w AS prev_docks,
                   epoch(snapshot_ts - lag(snapshot_ts) OVER w) / 3600.0 AS gap_h
            FROM fct_station_snapshot WINDOW w AS (PARTITION BY station_id ORDER BY snapshot_ts)
        ), y AS (
            SELECT *, bikes - bikes_delta AS prev_bikes FROM x
            WHERE is_installed AND is_renting AND is_returning AND NOT is_stuck_excluded
              AND bikes_delta IS NOT NULL AND local_date IN (SELECT local_date FROM days)
        )
        SELECT station_id, hour_of_day, local_date,
               coalesce(sum(CASE WHEN bikes_delta < 0 AND -bikes_delta < {jump} THEN -bikes_delta ELSE 0 END)
                        FILTER (WHERE prev_bikes > 0), 0) AS pk,
               coalesce(sum(gap_h) FILTER (WHERE prev_bikes > 0), 0) AS exp_out,
               coalesce(sum(CASE WHEN bikes_delta > 0 AND bikes_delta < {jump} THEN bikes_delta ELSE 0 END)
                        FILTER (WHERE prev_docks > 0), 0) AS rt,
               coalesce(sum(gap_h) FILTER (WHERE prev_docks > 0), 0) AS exp_in
        FROM y GROUP BY ALL
        """
    ).df()
    jumps = con.execute(
        f"""
        WITH x AS (SELECT local_date, bikes_delta FROM fct_station_snapshot
                   WHERE is_installed AND bikes_delta IS NOT NULL AND local_date IN (SELECT local_date FROM days))
        SELECT count(*) FILTER (WHERE bikes_delta >= {jump}) AS jumps_up, count(*) FILTER (WHERE bikes_delta <= -{jump}) AS jumps_down,
               count(DISTINCT local_date) AS n_days FROM x
        """
    ).df().iloc[0]
    stations = con.execute(
        "SELECT station_id, arg_max(capacity, snapshot_ts) AS capacity FROM fct_station_snapshot WHERE is_installed GROUP BY 1"
    ).df().set_index("station_id")
    init = con.execute(
        "SELECT station_id, avg(bikes) AS init_bikes FROM fct_station_snapshot WHERE is_installed AND hour_of_day = 0 "
        "AND local_date IN (SELECT local_date FROM days) GROUP BY 1"
    ).df().set_index("station_id")
    lv = con.execute(
        "SELECT hour_of_day, avg(bikes) AS b FROM fct_station_snapshot WHERE is_installed AND is_renting AND NOT is_stuck_excluded "
        "AND local_date IN (SELECT local_date FROM days) GROUP BY 1 ORDER BY 1"
    ).df().set_index("hour_of_day")["b"]
    con.close()

    tot = agg.groupby("station_id")[["exp_out", "exp_in"]].sum()
    keep = tot[(tot["exp_out"] >= min_exposure_h) & (tot["exp_in"] >= min_exposure_h)].index
    keep = [s for s in keep if s in stations.index and pd.notna(stations.loc[s, "capacity"]) and s in init.index]
    excluded = int(len(tot) - len(keep))
    a = agg[agg["station_id"].isin(keep)]

    def rates(ev: str, ex: str) -> np.ndarray:
        sh = a.groupby(["station_id", "hour_of_day"])[[ev, ex]].sum()
        st_rate = a.groupby("station_id")[ev].sum() / a.groupby("station_id")[ex].sum()
        city_h = a.groupby("hour_of_day")[ev].sum() / a.groupby("hour_of_day")[ex].sum()
        city_all = a[ev].sum() / a[ex].sum()
        out = np.zeros((24, len(keep)))
        for j, s in enumerate(keep):
            for h in range(24):
                n, e = (sh.loc[(s, h), ev], sh.loc[(s, h), ex]) if (s, h) in sh.index else (0.0, 0.0)
                prior = st_rate[s] * city_h.get(h, city_all) / city_all
                out[h, j] = (n + SHRINK_K_H * prior) / (e + SHRINK_K_H)
        return out

    # base_in only provides the SHAPE of where and when bikes come back; the simulator conserves bikes by returning
    # the pickups it actually served (see engine.returns_at), so the level of the raw return estimate is not used.
    base_out, base_in = rates("pk", "exp_out"), rates("rt", "exp_in")

    # day-to-day variation: station-day counts versus what the station's average rate predicts
    sd = a.groupby(["station_id", "local_date"])[["pk", "exp_out"]].sum().reset_index()
    st_rate = a.groupby("station_id")["pk"].sum() / a.groupby("station_id")["exp_out"].sum()
    sd["expected"] = sd["station_id"].map(st_rate) * sd["exp_out"]
    city = sd.groupby("local_date")[["pk", "expected"]].sum()
    ratio = city["pk"] / city["expected"]
    sigma_city = float(np.log(ratio).std(ddof=1))
    sd["q"] = sd["pk"] / (sd["expected"] * sd["local_date"].map(ratio))
    good = sd[(sd["pk"] >= 5) & (sd["q"] > 0)]
    var_obs = float(np.log(good["q"]).var(ddof=1))
    poisson_var = float((1.0 / good["pk"]).mean())      # delta-method variance of log(count) from pure counting noise
    sigma_station = float(np.sqrt(max(0.0, var_obs - poisson_var)))

    # extra-Poisson variation of hourly counts, after removing city-day and station-day levels (method of moments, approximate)
    a2 = a.merge(sd[["station_id", "local_date", "q"]], on=["station_id", "local_date"])
    a2 = a2[(a2["q"] > 0) & (a2["exp_out"] > 0.5)].copy()
    a2["x"] = a2["pk"] / a2["exp_out"] / (a2["local_date"].map(ratio) * a2["q"])
    cell = a2.groupby(["station_id", "hour_of_day"])["x"].agg(["mean", "var", "count"])
    cell = cell[cell["count"] >= 10]
    dispersion = float(max(0.0, (cell["var"] - cell["mean"]).sum() / (cell["mean"] ** 2).sum()))

    # Average trip time by Little's law: bikes in use (the dip of the station level below its night level, times the number
    # of stations) = trips per hour x average trip time. Counted pickups understate true trips, so this is consistent with the
    # simulator's own (counted) demand rather than with true trip times; trucks and night activity make it approximate.
    night, day_mean = float(lv.loc[[3, 4, 5]].mean()), float(lv.mean())
    trip_hours = float(np.clip(len(keep) * max(night - day_mean, 0.0) / (base_out.sum() / 24.0), 0.05, 0.9))

    n_days = int(jumps["n_days"])
    summary = {
        "n_stations_simulated": len(keep), "n_stations_excluded_low_exposure": excluded, "n_days_used": n_days,
        "jump_threshold_bikes": jump, "jumps_up_per_day": float(jumps["jumps_up"]) / n_days,
        "jumps_down_per_day": float(jumps["jumps_down"]) / n_days,
        "counted_pickups_per_station_day_mean": float(base_out.sum(axis=0).mean()),
        "counted_returns_per_station_day_mean": float(base_in.sum(axis=0).mean()),
        "sigma_city_day": sigma_city, "sigma_station_day": sigma_station, "hourly_dispersion": dispersion, "night_station_level_bikes": night, "day_mean_station_level_bikes": day_mean, "trip_hours": trip_hours, "capacity_mean": float(stations.loc[keep, "capacity"].mean()),
    }
    cap = stations.loc[keep, "capacity"].to_numpy(float)
    init_b = np.clip(np.round(init.loc[keep, "init_bikes"].to_numpy(float)), 0, cap)
    return Params(list(keep), cap, init_b, base_out, base_in, sigma_city, sigma_station, summary, dispersion, trip_hours)


def save_params(p: Params, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"station_id": p.station_ids, "capacity": p.capacity, "init_bikes": p.init_bikes}).to_csv(out_dir / "stations.csv", index=False)
    rows = [(s, h, p.base_out[h, j], p.base_in[h, j]) for j, s in enumerate(p.station_ids) for h in range(24)]
    pd.DataFrame(rows, columns=["station_id", "hour", "pickups_per_h", "returns_per_h"]).round(5).to_csv(out_dir / "demand_rates.csv", index=False)
    (out_dir / "summary.json").write_text(json.dumps({**p.summary}, indent=2), encoding="utf-8")


def load_params(out_dir: Path) -> Params:
    st = pd.read_csv(out_dir / "stations.csv", dtype={"station_id": str})
    dr = pd.read_csv(out_dir / "demand_rates.csv", dtype={"station_id": str})
    ids = list(st["station_id"])
    bo = dr.pivot(index="hour", columns="station_id", values="pickups_per_h")[ids].to_numpy()
    bi = dr.pivot(index="hour", columns="station_id", values="returns_per_h")[ids].to_numpy()
    s = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    return Params(ids, st["capacity"].to_numpy(float), st["init_bikes"].to_numpy(float), bo, bi, s["sigma_city_day"], s["sigma_station_day"], s, s.get("hourly_dispersion", 0.0), s.get("trip_hours", 0.3))


# ----------------------------------------------------------------------------- the simulated world
def make_world(p: Params, cfg: dict, seed: int, demand_scale: float = 1.0) -> World:
    rng = np.random.default_rng(seed)
    n, days = len(p.station_ids), cfg["system"]["n_days"]
    T = days * 24
    city = rng.lognormal(-p.sigma_city**2 / 2, p.sigma_city, days)                      # mean 1
    stn = rng.lognormal(-p.sigma_station**2 / 2, p.sigma_station, (days, n))            # mean 1
    lam_out = np.empty((T, n))
    dest_p = np.empty((T, n))
    for t in range(T):
        h, d = t % 24, t // 24
        lam_out[t] = p.base_out[h] * demand_scale * city[d] * stn[d]
        w = p.base_in[h] * stn[d]
        dest_p[t] = w / w.sum()
    # expected returns in hour t = this hour's and last hour's expected pickups spread by dest_p (used by the forecast-driven policy)
    th = float(np.clip(1.0 - p.trip_hours, 0.0, 1.0))
    prev_total = np.concatenate([[lam_out[0].sum()], lam_out[:-1].sum(axis=1)])
    lam_in = (th * lam_out.sum(axis=1) + (1 - th) * prev_total)[:, None] * dest_p
    k = min(cfg["rebalancing"]["static_route_stations"], n)
    if p.dispersion > 0:   # bursty arrivals: gamma-mixed Poisson with mean-1 gamma of variance `dispersion`
        shape = 1.0 / p.dispersion
        eff_out = lam_out * rng.gamma(shape, 1.0 / shape, lam_out.shape)
    else:
        eff_out = lam_out
    return World(capacity=p.capacity.astype(int), lam_out=lam_out, lam_in=lam_in, pickups=rng.poisson(eff_out), returns=np.zeros_like(lam_out, dtype=int),
                 static_route=rng.choice(n, size=k, replace=False), init_bikes=p.init_bikes.astype(int),
                 dest_p=dest_p, u_ret=rng.random((T, n)), trip_same_hour=th)


def trajectory_none(world: World) -> tuple[np.ndarray, np.ndarray]:
    """Bike counts BEFORE each hour (T, N) and AFTER each hour (T, N) when nobody rebalances."""
    T = world.pickups.shape[0]
    cap = world.capacity
    bikes = world.init_bikes.copy()
    before = np.empty((T, cap.size))
    after = np.empty((T, cap.size))
    served_prev = float(world.lam_in[0].sum())
    carry = 0.0
    for t in range(T):
        before[t] = bikes
        sp = np.minimum(world.pickups[t], bikes)
        bikes = bikes - sp
        served_now = float(sp.sum())
        r = returns_at(world, t, served_prev, served_now, carry)
        sr = np.minimum(r, cap - bikes)
        bikes = bikes + sr
        carry = float((r - sr).sum())
        served_prev = served_now
        after[t] = bikes
    return before, after


# ----------------------------------------------------------------------------- calibrating forecast noise to measured accuracy
def stockout_scores(p: Params, cfg: dict, horizon: int, noise_sds, reps: int, seed: int, demand_scale: float = 1.0) -> dict:
    """AUC of 'projected level' as a predictor of 'this station hits zero bikes within the next `horizon` hours'
    (no rebalancing), at each round hour, for several forecast-noise levels. Returns {sd: auc, 'reactive': auc}."""
    rounds = cfg["rebalancing"]["round_hours"]
    ys, scores = [], {sd: [] for sd in noise_sds}
    react = []
    rng = np.random.default_rng(seed + 999)
    for r in range(reps):
        w = make_world(p, cfg, seed + r, demand_scale)
        before, after = trajectory_none(w)
        T = before.shape[0]
        for t in range(T - horizon):
            if t % 24 not in rounds:
                continue
            ys.append((after[t:t + horizon].min(axis=0) == 0).astype(int))
            f = (w.lam_out[t:t + horizon] - w.lam_in[t:t + horizon]).sum(axis=0)
            for sd in noise_sds:
                scores[sd].append(-(before[t] - (f + rng.normal(0, sd, f.size))))
            react.append(-before[t])
    y = np.concatenate(ys)
    out = {sd: float(roc_auc_score(y, np.concatenate(v))) for sd, v in scores.items()}
    out["reactive"] = float(roc_auc_score(y, np.concatenate(react)))
    out["event_rate"] = float(y.mean())
    return out


def calibrate_noise(p: Params, cfg: dict, targets: dict, grid=(0, 0.5, 1, 2, 3, 4, 6, 8, 12), reps: int = 30, seed: int = 7) -> dict:
    """For each horizon H (hours) find the forecast-noise sd (bikes) whose implied AUC equals the measured AUC."""
    res = {}
    for H, target in targets.items():
        a = stockout_scores(p, cfg, H, grid, reps, seed)
        xs = np.array(grid, float)
        ys = np.array([a[g] for g in grid])
        if target >= ys[0]:
            sd, note = 0.0, "target AUC is not reachable even with no forecast noise; using noise 0"
        elif target <= ys[-1]:
            sd, note = float(xs[-1]), "target AUC is below the AUC at the largest noise level; using the largest"
        else:
            sd, note = float(np.interp(target, ys[::-1], xs[::-1])), ""
        res[H] = {"target_auc": target, "noise_sd_bikes": sd, "auc_no_noise": ys[0], "auc_reactive": a["reactive"],
                  "event_rate": a["event_rate"], "grid": {float(g): float(a[g]) for g in grid}, "note": note}
    return res


def measured_aucs(docs_dir: Path) -> dict:
    """Read the GBM AUC at 1, 3 and 6 hours from the forecast results files (generated by src/forecast/evaluate.py)."""
    files = {1: "forecast_results.md", 3: "forecast_results_h3.md", 6: "forecast_results_h6.md"}
    out = {}
    for h, f in files.items():
        txt = (docs_dir / f).read_text(encoding="utf-8")
        header = re.search(r"\| model \| base_rate \|[^\n]*\n", txt).group(0).strip().strip("|").split("|")
        cols = [c.strip() for c in header]
        row = re.search(r"\| gbm \|[^\n]*\n", txt).group(0).strip().strip("|").split("|")
        out[h] = float(row[cols.index("auc")])
    return out


# ----------------------------------------------------------------------------- policy comparison
def policy_specs(calib: dict) -> list[dict]:
    specs = [{"name": "none", "policy": "none"}, {"name": "static", "policy": "static"}, {"name": "reactive", "policy": "reactive"}]
    for H, c in calib.items():
        specs.append({"name": f"forecast_{H}h", "policy": "forecast", "lookahead": H, "noise": c["noise_sd_bikes"]})
    h3 = 3 if 3 in calib else sorted(calib)[0]
    specs.append({"name": f"oracle_{h3}h", "policy": "forecast", "lookahead": h3, "noise": 0.0})
    return specs


def run_scenario(p: Params, cfg: dict, specs: list[dict], reps: int, seed: int, demand_scale: float = 1.0, transfers_per_round: int | None = None) -> pd.DataFrame:
    c = json.loads(json.dumps(cfg))   # deep copy
    if transfers_per_round is not None:
        c["rebalancing"]["n_trucks"], c["rebalancing"]["transfers_per_truck_per_round"] = 1, int(transfers_per_round)
    rows = []
    days = c["system"]["n_days"]
    for rep in range(reps):
        w = make_world(p, c, seed + rep, demand_scale)
        for sp in specs:
            c2 = json.loads(json.dumps(c))
            if sp["policy"] == "forecast":
                c2["rebalancing"]["lookahead_h"] = sp["lookahead"]
                c2["forecast"]["rel_noise"], c2["forecast"]["abs_noise"] = 0.0, sp["noise"]
            res = run_policy(w, c2, sp["policy"], np.random.default_rng(50_000 + seed + rep))
            res.update(name=sp["name"], rep=rep, lost_pickups_per_day=res["lost_pickups"] / days,
                       stockout_hours_per_day=res["stockout_station_hours"] / days, transfers_per_day=res["transfers"] / days)
            rows.append(res)
    return pd.DataFrame(rows)


def mean_ci(x: pd.Series) -> tuple[float, float, float]:
    """Mean and 95 % confidence interval for the mean (normal approximation over independent replications)."""
    x = pd.Series(x).dropna()
    se = float(x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 1 else float("nan")
    return float(x.mean()), float(x.mean() - 1.96 * se), float(x.mean() + 1.96 * se)


def summarize(df: pd.DataFrame, baseline: str = "none") -> pd.DataFrame:
    """Per policy: mean lost pickups per day and the paired reduction versus `baseline` with a 95 % confidence interval for the mean."""
    base = df[df["name"] == baseline].set_index("rep")["lost_pickups_per_day"]
    rows = []
    for name, g in df.groupby("name", sort=False):
        g = g.set_index("rep")
        d = base - g["lost_pickups_per_day"]
        rows.append({"policy": name, "service_level": g["service_level"].mean(), "lost_pickups_per_day": g["lost_pickups_per_day"].mean(),
                     "stockout_station_hours_per_day": g["stockout_hours_per_day"].mean(), "transfers_per_day": g["transfers_per_day"].mean(),
                     f"avoided_vs_{baseline}": mean_ci(d)[0], "avoided_ci_lo": mean_ci(d)[1], "avoided_ci_hi": mean_ci(d)[2],
                     "sd_across_replications": d.std(ddof=1)})
    return pd.DataFrame(rows)


def paired_difference(df: pd.DataFrame, a: str, b: str) -> tuple[float, float, float]:
    """Lost pickups per day avoided by policy `a` relative to policy `b` (positive = a is better): mean and 95 % CI for the mean."""
    x = df[df["name"] == b].set_index("rep")["lost_pickups_per_day"] - df[df["name"] == a].set_index("rep")["lost_pickups_per_day"]
    return mean_ci(x)


# ----------------------------------------------------------------------------- validation against the real network
def validation(p: Params, cfg: dict, db: Path, reps: int = 8, seed: int = 500, demand_scale: float = 1.0) -> dict:
    """How closely does the simulated network (no rebalancing) resemble the real one? Real shares are the headline
    (eligible) stockout/blockout shares of 10-minute snapshots; simulated shares are end-of-hour states."""
    con = duckdb.connect(str(db), read_only=True)
    con.execute("SET TimeZone='UTC'")
    real_st = con.execute(
        "SELECT station_id, avg(is_stockout::int) FILTER (WHERE is_stockout_eligible) AS empty, "
        "avg(is_blockout::int) FILTER (WHERE is_blockout_eligible) AS full, avg(bikes) AS mean_bikes "
        "FROM fct_station_snapshot WHERE is_installed GROUP BY 1"
    ).df().set_index("station_id")
    real_h = con.execute(
        "SELECT hour_of_day, avg(is_stockout::int) FILTER (WHERE is_stockout_eligible) AS empty, "
        "avg(is_blockout::int) FILTER (WHERE is_blockout_eligible) AS full FROM fct_station_snapshot WHERE is_installed GROUP BY 1 ORDER BY 1"
    ).df().set_index("hour_of_day")
    real_all = con.execute(
        "SELECT avg(is_stockout::int) FILTER (WHERE is_stockout_eligible) AS empty, avg(is_blockout::int) FILTER (WHERE is_blockout_eligible) AS full, "
        "avg(bikes) FILTER (WHERE is_installed) AS mean_bikes FROM fct_station_snapshot WHERE is_installed"
    ).df().iloc[0]
    con.close()

    n = len(p.station_ids)
    emp, ful, mb, hod_e, hod_f = [], [], [], [], []
    for r in range(reps):
        w = make_world(p, cfg, seed + r, demand_scale)
        _, after = trajectory_none(w)
        emp.append((after == 0).mean(axis=0))
        ful.append((after == w.capacity).mean(axis=0))
        mb.append(after.mean(axis=0))
        T = after.shape[0]
        hod_e.append((after == 0).mean(axis=1).reshape(T // 24, 24).mean(axis=0))
        hod_f.append((after == w.capacity).mean(axis=1).reshape(T // 24, 24).mean(axis=0))
    sim_st = pd.DataFrame({"empty": np.mean(emp, axis=0), "full": np.mean(ful, axis=0), "mean_bikes": np.mean(mb, axis=0)}, index=p.station_ids)
    j = sim_st.join(real_st, lsuffix="_sim", rsuffix="_real", how="inner")
    overall = pd.DataFrame([
        {"measure": "share of station-time empty", "real": real_all["empty"], "simulated_no_rebalancing": sim_st["empty"].mean()},
        {"measure": "share of station-time full", "real": real_all["full"], "simulated_no_rebalancing": sim_st["full"].mean()},
        {"measure": "mean bikes per station", "real": real_all["mean_bikes"], "simulated_no_rebalancing": sim_st["mean_bikes"].mean()},
    ])
    ranks = pd.DataFrame([{"measure": k, "spearman_across_stations": j[f"{k}_sim"].corr(j[f"{k}_real"], method="spearman"), "stations": len(j)}
                          for k in ("empty", "full", "mean_bikes")])
    se, sf = np.mean(hod_e, axis=0), np.mean(hod_f, axis=0)
    blocks = {"night 00-05": range(0, 6), "morning 06-11": range(6, 12), "afternoon 12-17": range(12, 18), "evening 18-23": range(18, 24)}
    prof = pd.DataFrame([{"madrid_hours": b, "real_empty": real_h.loc[list(h), "empty"].mean(), "sim_empty": se[list(h)].mean(),
                          "real_full": real_h.loc[list(h), "full"].mean(), "sim_full": sf[list(h)].mean()} for b, h in blocks.items()])
    shape = pd.DataFrame([{"measure": "empty share by hour of day", "pearson_real_vs_sim": float(np.corrcoef(real_h["empty"].to_numpy(), se)[0, 1])},
                          {"measure": "full share by hour of day", "pearson_real_vs_sim": float(np.corrcoef(real_h["full"].to_numpy(), sf)[0, 1])}])
    return {"overall": overall, "ranks": ranks, "blocks": prof, "shape": shape}
