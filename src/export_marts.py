"""Export the dbt marts to CSV for the Shiny dashboard (so R needs only shiny/ggplot2/dplyr).

    python src/export_marts.py --db dbt/target/valenbisi.duckdb --out dashboard/data [--synthetic]

Writes kpi_service_level.csv, seg_station_abc_xyz.csv, dim_station.csv, fct_run_health.csv and
meta.csv (data span, number of days, and whether the data is synthetic) so the app can show an
honest banner.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
import pandas as pd

TABLES = ["kpi_service_level", "seg_station_abc_xyz", "dim_station", "fct_run_health"]


def export(db: str, out: Path, synthetic: bool) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(db, read_only=True)
    con.sql("SET TimeZone='UTC'")  # print instants in UTC, not the machine's zone
    try:
        for t in TABLES:
            con.sql(f"select * from {t}").df().to_csv(out / f"{t}.csv", index=False)
        span = con.sql(
            "select min(snapshot_ts) as first_ts, max(snapshot_ts) as last_ts, "
            "count(distinct cast(timezone('Europe/Madrid', snapshot_ts) as date)) as n_days, "
            "count(*) as n_snapshots from fct_station_snapshot"
        ).df().iloc[0]
    finally:
        con.close()
    meta = {"first_ts": str(span["first_ts"]), "last_ts": str(span["last_ts"]),
            "n_days": int(span["n_days"]), "n_snapshots": int(span["n_snapshots"]),
            "synthetic": bool(synthetic)}
    pd.DataFrame([meta]).to_csv(out / "meta.csv", index=False)
    return meta


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--synthetic", action="store_true")
    a = ap.parse_args()
    print(export(a.db, a.out, a.synthetic))
