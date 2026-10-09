"""Run the rebalancing Monte Carlo and print a summary.

    python src/simulate/run.py [--config src/simulate/config.toml] [--out sim_results.csv]

Output is labelled ASSUMPTION-DRIVEN: it shows how policies compare under the config's assumed demand and
forecast quality. It is not a statement about real Valenbisi performance.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simulate.engine import load_config, monte_carlo  # noqa: E402


def summarize(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    g = df.groupby("policy")
    out = pd.DataFrame({
        "service_level_mean": g["service_level"].mean(),
        "service_level_lo95": g["service_level"].quantile(0.025),
        "service_level_hi95": g["service_level"].quantile(0.975),
        "lost_pickups_mean": g["lost_pickups"].mean(),
        "lost_returns_mean": g["lost_returns"].mean(),
        "transfers_mean": g["transfers"].mean(),
    })
    # paired difference against "none": same world per replication
    base = df[df["policy"] == "none"].set_index("rep")["lost_pickups"]
    diffs = {}
    for pol, grp in df.groupby("policy"):
        d = (base - grp.set_index("rep")["lost_pickups"])
        diffs[pol] = (d.mean(), d.quantile(0.025), d.quantile(0.975))
    out["lost_pickups_avoided_vs_none"] = {k: v[0] for k, v in diffs.items()}
    out["avoided_lo95"] = {k: v[1] for k, v in diffs.items()}
    out["avoided_hi95"] = {k: v[2] for k, v in diffs.items()}
    return out.loc[["none", "static", "reactive", "forecast"]]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--config", default=str(Path(__file__).with_name("config.toml")))
    ap.add_argument("--out", default=None, help="optional CSV of per-replication results")
    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    rows = monte_carlo(cfg)
    print("== Rebalancing simulation: ASSUMPTION-DRIVEN, not a result about real Valenbisi data ==")
    print(f"config: {a.config}; replications: {cfg['monte_carlo']['n_replications']}\n")
    print(summarize(rows).round(3).to_string())
    if a.out:
        pd.DataFrame(rows).to_csv(a.out, index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
