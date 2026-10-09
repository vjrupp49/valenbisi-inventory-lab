"""Health report for collected snapshots. Usage: python src/check_data.py <data_dir>

Answers the morning-after questions: is data flowing, how big are the gaps, is the upstream
feed actually fresh, and how many stations have gone quiet?
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb


def main(root: str) -> int:
    root_p = Path(root)
    if not list(root_p.glob("run_meta/dt=*/*.parquet")):
        print(f"No run_meta files under {root_p}. Has the workflow run yet?")
        return 1

    con = duckdb.connect()
    con.sql(
        f"CREATE VIEW meta AS SELECT * FROM "
        f"read_parquet('{root_p}/run_meta/*/*.parquet', hive_partitioning=true, union_by_name=true)"
    )

    print("\n== Runs ==")
    con.sql(
        """
        SELECT count(*) AS runs,
               count(*) FILTER (WHERE ok) AS ok_runs,
               round(100.0 * count(*) FILTER (WHERE NOT ok) / count(*), 1) AS error_pct,
               min(snapshot_ts) AS first_run,
               max(snapshot_ts) AS last_run
        FROM meta
        """
    ).show()

    print("== Runs per day ==")
    con.sql("SELECT dt, count(*) AS runs, count(*) FILTER (WHERE ok) AS ok_runs FROM meta GROUP BY dt ORDER BY dt").show()

    print("== Largest gaps between runs (minutes) ==")
    con.sql(
        """
        SELECT snapshot_ts, round(date_diff('second', lag(snapshot_ts) OVER (ORDER BY snapshot_ts), snapshot_ts) / 60.0, 1) AS gap_min
        FROM meta ORDER BY gap_min DESC NULLS LAST LIMIT 5
        """
    ).show()

    print("== Upstream freshness (is the feed actually live?) ==")
    con.sql(
        """
        SELECT round(median(feed_age_s), 1) AS median_feed_age_s,
               round(max(feed_age_s), 1) AS max_feed_age_s,
               round(median(n_stale_1h), 0) AS median_stale_stations,
               round(median(n_installed), 0) AS median_installed
        FROM meta WHERE ok
        """
    ).show()

    if list(root_p.glob("station_status/dt=*/*.parquet")):
        con.sql(
            f"CREATE VIEW status AS SELECT * FROM "
            f"read_parquet('{root_p}/station_status/*/*.parquet', hive_partitioning=true, union_by_name=true)"
        )
        print("== Station rows ==")
        con.sql(
            """
            SELECT count(*) AS rows, count(DISTINCT station_id) AS stations,
                   count(DISTINCT snapshot_ts) AS snapshots
            FROM status
            """
        ).show()
        print("== Stations whose bike count changed at least once ==")
        con.sql(
            """
            SELECT count(*) FILTER (WHERE n_distinct > 1) AS changing,
                   count(*) FILTER (WHERE n_distinct = 1) AS never_changed
            FROM (SELECT station_id, count(DISTINCT num_vehicles_available) AS n_distinct FROM status GROUP BY 1)
            """
        ).show()
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
