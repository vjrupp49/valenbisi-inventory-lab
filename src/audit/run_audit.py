"""Data integrity audit for the collected Valenbisi snapshots. Every number in the integrity report comes from here.

    python src/audit/run_audit.py --data data_frozen --out docs/data_integrity_results.md [--dbt-db dbt/target/valenbisi.duckdb]

It only READS the parquet files (and optionally the dbt DuckDB file) and writes one markdown file of tables,
grouped by the questions in docs/analysis_plan.md (Phase 1, sections A-G). Re-run it on a newer dataset to see
what changes. Times are UTC unless a column says "madrid".
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

# A station-snapshot is only compared with the previous one when they are at most this far apart,
# so a collection gap is not mistaken for a change.
PAIR_MAX_GAP_MIN = 15


def setup(con: duckdb.DuckDBPyConnection, root: Path) -> None:
    con.sql("SET TimeZone='UTC'")
    r = root.as_posix()
    for view, folder in (("st", "station_status"), ("rm", "run_meta"), ("si", "station_information")):
        con.sql(
            f"CREATE VIEW {view} AS SELECT * FROM read_parquet('{r}/{folder}/*/*.parquet', "
            "hive_partitioning=true, union_by_name=true)"
        )
    # One row per station-snapshot with the previous snapshot's values alongside (for change detection).
    con.sql(
        """
        CREATE TABLE pairs AS
        SELECT station_id, snapshot_ts AS t, is_installed AS inst, is_renting AS rent, is_returning AS ret,
               num_vehicles_available AS b, num_docks_available AS d,
               num_vehicles_disabled AS bd, num_docks_disabled AS dd,
               last_reported AS lr, snapshot_ts - last_reported AS age,
               lag(num_vehicles_available) OVER w AS pb,
               lag(last_reported) OVER w AS plr,
               snapshot_ts - lag(snapshot_ts) OVER w AS gap
        FROM st WINDOW w AS (PARTITION BY station_id ORDER BY snapshot_ts)
        """
    )
    # Latest known capacity per station (capacity can change; see check B4).
    con.sql("CREATE VIEW cap AS SELECT station_id, arg_max(capacity, snapshot_ts) AS cap FROM si GROUP BY 1")


G = f"pb IS NOT NULL AND gap <= INTERVAL {PAIR_MAX_GAP_MIN} MINUTE AND inst"  # usable consecutive pairs, installed stations

CHECKS: list[tuple[str, str, str, str]] = [
    # (section, id, title, sql)
    ("A. Completeness", "A1", "Overview",
     "SELECT count(*) AS station_rows, count(DISTINCT snapshot_ts) AS snapshots, count(DISTINCT station_id) AS stations, "
     "min(snapshot_ts) AS first_snapshot, max(snapshot_ts) AS last_snapshot FROM st"),
    ("A. Completeness", "A2", "Snapshots per UTC day (nominal 144)",
     "SELECT cast(snapshot_ts AS date) AS utc_day, count(DISTINCT snapshot_ts) AS snapshots, "
     "count(DISTINCT snapshot_ts) - 144 AS vs_144 FROM st GROUP BY 1 ORDER BY 1"),
    ("A. Completeness", "A3", "Gaps between consecutive snapshots, minutes (distribution)",
     "WITH g AS (SELECT epoch(t - lag(t) OVER (ORDER BY t))/60 AS m FROM (SELECT DISTINCT snapshot_ts AS t FROM st)) "
     "SELECT count(m) AS gaps, quantile_cont(m, 0.5) AS median_min, quantile_cont(m, 0.99) AS p99_min, max(m) AS max_min, "
     "count(*) FILTER (WHERE m > 11) AS over_11min, count(*) FILTER (WHERE m > 15) AS over_15min, "
     "count(*) FILTER (WHERE m > 60) AS over_60min FROM g"),
    ("A. Completeness", "A3b", "Every gap over 15 minutes",
     "WITH g AS (SELECT t, epoch(t - lag(t) OVER (ORDER BY t))/60 AS m FROM (SELECT DISTINCT snapshot_ts AS t FROM st)) "
     "SELECT t AS snapshot_after_gap, round(m, 1) AS gap_min FROM g WHERE m > 15 ORDER BY t"),
    ("A. Completeness", "A4", "Stations per snapshot",
     "SELECT n AS stations_in_snapshot, count(*) AS snapshots, min(t) AS first_seen, max(t) AS last_seen "
     "FROM (SELECT snapshot_ts AS t, count(*) AS n FROM st GROUP BY 1) GROUP BY n ORDER BY n"),
    ("A. Completeness", "A5", "Runs versus snapshots with station rows",
     "SELECT (SELECT count(*) FROM rm) AS runs, (SELECT count(*) FROM rm WHERE ok) AS ok_runs, "
     "(SELECT count(DISTINCT snapshot_ts) FROM st) AS snapshots_with_rows, "
     "(SELECT count(*) FROM rm WHERE ok AND snapshot_ts NOT IN (SELECT snapshot_ts FROM st)) AS ok_runs_without_rows, "
     "(SELECT count(DISTINCT snapshot_ts) FROM st WHERE snapshot_ts NOT IN (SELECT snapshot_ts FROM rm)) AS snapshots_without_run"),
    ("A. Completeness", "A6", "Duplicates, partition mismatch, nulls",
     "SELECT (SELECT count(*) FROM (SELECT 1 FROM st GROUP BY station_id, snapshot_ts HAVING count(*) > 1)) AS duplicate_station_snapshots, "
     "count(*) FILTER (WHERE cast(snapshot_ts AS date) <> dt) AS folder_date_mismatch, "
     "count(*) - count(num_vehicles_available) AS null_bikes, count(*) - count(num_docks_available) AS null_docks, "
     "count(*) - count(is_installed) AS null_installed, count(*) - count(last_reported) AS null_last_reported, "
     "count(*) - count(feed_last_updated) AS null_feed_ts FROM st"),
    ("A. Completeness", "A7", "Repeated feed timestamps / identical consecutive snapshots (stale feed served twice?)",
     "WITH f AS (SELECT snapshot_ts, any_value(feed_last_updated) AS fu, "
     "md5(string_agg(station_id || ':' || num_vehicles_available, ',' ORDER BY station_id)) AS h FROM st GROUP BY 1), "
     "g AS (SELECT fu, h, lag(fu) OVER (ORDER BY snapshot_ts) AS pfu, lag(h) OVER (ORDER BY snapshot_ts) AS ph FROM f) "
     "SELECT count(*) AS snapshots, count(*) FILTER (WHERE fu = pfu) AS repeated_feed_ts, count(*) FILTER (WHERE h = ph) AS identical_to_previous FROM g"),
    ("A. Completeness", "A7b", "Age of the feed's own timestamp at collection time, seconds (run_meta.feed_age_s)",
     "SELECT count(feed_age_s) AS runs, round(quantile_cont(feed_age_s, 0.5), 1) AS median_s, round(quantile_cont(feed_age_s, 0.99), 1) AS p99_s, "
     "round(max(feed_age_s), 1) AS max_s FROM rm"),
    ("A. Completeness", "A8", "Clock change (Madrid, 2026-10-25): distinct real hours that share a local hour label",
     "SELECT hour(timezone('Europe/Madrid', t)) AS madrid_hour, count(DISTINCT date_trunc('hour', t)) AS distinct_utc_hours "
     "FROM generate_series(timestamptz '2026-10-24 22:00:00+00', timestamptz '2026-10-25 22:50:00+00', INTERVAL 10 MINUTE) g(t) "
     "WHERE cast(timezone('Europe/Madrid', t) AS date) = date '2026-10-25' GROUP BY 1 HAVING count(DISTINCT date_trunc('hour', t)) > 1"),

    ("B. Validity", "B1", "Installed / renting / returning combinations",
     "SELECT is_installed, is_renting, is_returning, count(*) AS station_snapshots, count(DISTINCT station_id) AS stations "
     "FROM st GROUP BY ALL ORDER BY 4 DESC"),
    ("B. Validity", "B2", "Bikes + free docks versus capacity (installed stations)",
     "SELECT count(*) AS n, count(*) FILTER (WHERE b + d = cap) AS equals_capacity, "
     "count(*) FILTER (WHERE b + d < cap) AS below_capacity, count(*) FILTER (WHERE b + d > cap) AS above_capacity, "
     "count(*) FILTER (WHERE b + d + bd + dd = cap) AS equals_with_disabled, "
     "count(*) FILTER (WHERE b + d + bd + dd < cap) AS still_below_with_disabled, "
     "count(*) FILTER (WHERE b + d + bd + dd > cap) AS above_with_disabled FROM pairs JOIN cap USING (station_id) WHERE inst"),
    ("B. Validity", "B3", "Impossible values",
     "SELECT count(*) FILTER (WHERE num_vehicles_available < 0 OR num_docks_available < 0) AS negative, "
     "count(*) FILTER (WHERE bikes_mechanical + bikes_other <> num_vehicles_available) AS bike_type_sum_mismatch, "
     "max(num_vehicles_disabled) AS max_disabled_bikes, max(num_docks_disabled) AS max_disabled_docks, "
     "count(*) FILTER (WHERE num_vehicles_disabled > 0) AS rows_with_disabled_bikes, "
     "count(*) FILTER (WHERE num_docks_disabled > 0) AS rows_with_disabled_docks FROM st"),
    ("B. Validity", "B4", "Station metadata that really changed over time (location tolerance 1e-5 degrees, about 1 m, to ignore rounding noise)",
     "SELECT station_id, capacity, name, min(snapshot_ts) AS first_seen, max(snapshot_ts) AS last_seen, count(*) AS daily_rows "
     "FROM si WHERE station_id IN (SELECT station_id FROM si GROUP BY 1 HAVING count(DISTINCT capacity) > 1 "
     "OR count(DISTINCT name) > 1 OR count(DISTINCT address) > 1 OR max(lat) - min(lat) > 1e-5 OR max(lon) - min(lon) > 1e-5) "
     "GROUP BY 1, 2, 3 ORDER BY 1, 4"),
    ("B. Validity", "B5", "Stations that were not installed at some point",
     "SELECT station_id, count(*) FILTER (WHERE NOT inst) AS rows_not_installed, count(*) AS rows_total, "
     "min(t) FILTER (WHERE NOT inst) AS first_not_installed, max(t) FILTER (WHERE NOT inst) AS last_not_installed, "
     "max(b) FILTER (WHERE NOT inst) AS max_bikes_while_not_installed FROM pairs GROUP BY 1 HAVING count(*) FILTER (WHERE NOT inst) > 0 "
     "ORDER BY 2 DESC"),
    ("B. Validity", "B6", "Installed but NOT renting (bikes cannot be taken): summary and top stations",
     "SELECT count(DISTINCT station_id) AS stations, count(*) AS station_snapshots, "
     "round(avg((b <> pb)::int) FILTER (WHERE pb IS NOT NULL), 4) AS bike_change_rate_while_not_renting "
     "FROM pairs WHERE inst AND NOT rent"),
    ("B. Validity", "B6b", "Installed but not renting: longest-affected stations",
     "SELECT station_id, count(*) AS snapshots, min(t) AS first_t, max(t) AS last_t, round(avg(b), 1) AS mean_bikes, "
     "round(avg((b = 0)::int), 2) AS share_zero_bikes FROM pairs WHERE inst AND NOT rent GROUP BY 1 ORDER BY 2 DESC LIMIT 8"),
    ("B. Validity", "B7", "Stations first seen after the first snapshot",
     "SELECT station_id, min(t) AS first_seen, count(*) AS snapshots FROM pairs GROUP BY 1 "
     "HAVING min(t) > (SELECT min(snapshot_ts) FROM st) + INTERVAL 1 HOUR"),

    ("C. Freshness (last_reported)", "C1", "Age of last_reported at snapshot time, installed stations",
     "SELECT round(quantile_cont(epoch(age)/3600.0, 0.1), 2) AS p10_hours, round(quantile_cont(epoch(age)/3600.0, 0.5), 2) AS median_hours, "
     "round(quantile_cont(epoch(age)/3600.0, 0.9), 2) AS p90_hours, round(quantile_cont(epoch(age)/3600.0, 0.99), 2) AS p99_hours "
     "FROM pairs WHERE inst"),
    ("C. Freshness (last_reported)", "C2", "Share flagged stale under different thresholds (installed stations)",
     "SELECT thr_h AS threshold_hours, round(avg((epoch(age)/3600.0 > thr_h)::int), 4) AS share_stale "
     "FROM pairs, (VALUES (0.5), (1), (3), (6), (12), (24)) v(thr_h) WHERE inst GROUP BY 1 ORDER BY 1"),
    ("C. Freshness (last_reported)", "C3", "Does last_reported move when the bike count moves? (consecutive snapshots, installed)",
     f"SELECT (b <> pb) AS bike_count_changed, (lr <> plr) AS last_reported_changed, count(*) AS station_intervals "
     f"FROM pairs WHERE {G} GROUP BY ALL ORDER BY 1, 2"),
    ("C. Freshness (last_reported)", "C3b", "Conditional rates from C3",
     f"SELECT round(avg((lr <> plr)::int) FILTER (WHERE b <> pb), 4) AS p_last_reported_moved_given_count_changed, "
     f"round(avg((b <> pb)::int) FILTER (WHERE lr <> plr), 4) AS p_count_changed_given_last_reported_moved, "
     f"round(avg((b <> pb)::int), 4) AS overall_count_change_rate FROM pairs WHERE {G}"),
    ("C. Freshness (last_reported)", "C4", "When does last_reported move? (UTC hour) and share stale >1h",
     f"SELECT hour(t) AS utc_hour, count(*) FILTER (WHERE lr <> plr) AS last_reported_moves, "
     f"round(avg((age > INTERVAL 1 HOUR)::int), 3) AS share_stale_1h FROM pairs WHERE {G} GROUP BY 1 ORDER BY 1"),

    ("D. Signal and resolution", "D1", "Bike-count changes per station between consecutive snapshots (installed stations)",
     f"WITH s AS (SELECT station_id, sum((b <> pb)::int) AS changes FROM pairs WHERE {G} GROUP BY 1), "
     "r AS (SELECT changes, row_number() OVER (ORDER BY changes DESC) AS rn, count(*) OVER () AS n FROM s) "
     "SELECT count(*) AS stations, count(*) FILTER (WHERE changes = 0) AS never_changed, "
     "quantile_cont(changes, 0.1) AS p10_changes, quantile_cont(changes, 0.5) AS median_changes, quantile_cont(changes, 0.9) AS p90_changes, "
     "round(sum(changes) FILTER (WHERE rn <= n * 0.1) * 1.0 / sum(changes), 3) AS top10pct_share_of_changes, "
     "round(sum(changes) FILTER (WHERE rn <= n * 0.5) * 1.0 / sum(changes), 3) AS top50pct_share_of_changes FROM r"),
    ("D. Signal and resolution", "D2", "Size of a bike-count change between snapshots",
     f"SELECT least(abs(b - pb), 10) AS abs_change_capped_at_10, count(*) AS station_intervals FROM pairs "
     f"WHERE {G} AND b <> pb GROUP BY 1 ORDER BY 1"),
    ("D. Signal and resolution", "D3", "Change rate and typical count by UTC hour",
     f"SELECT hour(t) AS utc_hour, round(avg((b <> pb)::int), 4) AS change_rate, round(avg(b), 2) AS mean_bikes "
     f"FROM pairs WHERE {G} GROUP BY 1 ORDER BY 1"),
    ("D. Signal and resolution", "D4", "Stockout and blockout prevalence",
     "SELECT count(*) FILTER (WHERE inst AND rent) AS rows_renting, round(avg((b = 0)::int) FILTER (WHERE inst AND rent), 4) AS stockout_share, "
     "count(*) FILTER (WHERE inst AND ret) AS rows_returning, round(avg((d = 0)::int) FILTER (WHERE inst AND ret), 4) AS blockout_share, "
     "count(DISTINCT station_id) FILTER (WHERE b = 0 AND inst AND rent) AS stations_with_any_stockout FROM pairs"),
    ("D. Signal and resolution", "D5", "Stockout episode length (consecutive snapshots at 0 bikes, installed + renting; 1 snapshot is about 10 min)",
     "WITH x AS (SELECT station_id, t, (b = 0 AND inst AND rent) AS so FROM pairs), "
     "y AS (SELECT *, sum((NOT so)::int) OVER (PARTITION BY station_id ORDER BY t) AS grp FROM x), "
     "z AS (SELECT station_id, grp, count(*) AS n FROM y WHERE so GROUP BY 1, 2) "
     "SELECT count(*) AS episodes, quantile_cont(n, 0.5) AS median_snapshots, quantile_cont(n, 0.9) AS p90_snapshots, "
     "count(*) FILTER (WHERE n = 1) AS one_snapshot_only, count(*) FILTER (WHERE n >= 144) AS at_least_1_day, "
     "count(*) FILTER (WHERE n >= 432) AS at_least_3_days FROM z"),
    ("D. Signal and resolution", "D6", "Chronically empty stations (share of snapshots at 0 bikes while renting)",
     "SELECT count(*) AS stations, count(*) FILTER (WHERE r >= 0.9) AS empty_90pct_or_more, count(*) FILTER (WHERE r >= 0.5) AS empty_50pct_or_more, "
     "count(*) FILTER (WHERE r >= 0.25) AS empty_25pct_or_more FROM (SELECT station_id, avg((b = 0)::int) AS r FROM pairs WHERE inst AND rent GROUP BY 1)"),
    ("D. Signal and resolution", "D7", "Longest stretch with no change in bike count (hours), top stations",
     "WITH x AS (SELECT station_id, t, b, (b <> lag(b) OVER (PARTITION BY station_id ORDER BY t))::int AS chg FROM pairs WHERE inst), "
     "y AS (SELECT *, sum(coalesce(chg, 0)) OVER (PARTITION BY station_id ORDER BY t) AS grp FROM x), "
     "z AS (SELECT station_id, grp, any_value(b) AS bikes, epoch(max(t) - min(t))/3600.0 AS hours FROM y GROUP BY 1, 2) "
     "SELECT station_id, round(max(hours), 1) AS longest_flat_hours, arg_max(bikes, hours) AS bikes_during FROM z GROUP BY 1 ORDER BY 2 DESC LIMIT 8"),
    ("D. Signal and resolution", "D8", "Share of installed-and-renting station-snapshots whose count has not changed for at least N hours",
     "WITH x AS (SELECT station_id, t, inst, rent, (b <> lag(b) OVER (PARTITION BY station_id ORDER BY t)) AS chg FROM pairs), "
     "y AS (SELECT *, max(CASE WHEN chg THEN t END) OVER (PARTITION BY station_id ORDER BY t ROWS UNBOUNDED PRECEDING) AS last_change FROM x), "
     "z AS (SELECT epoch(t - last_change)/3600.0 AS flat_h FROM y WHERE inst AND rent AND last_change IS NOT NULL) "
     "SELECT n_h AS flat_at_least_hours, round(avg((flat_h >= n_h)::int), 4) AS share_of_snapshots FROM z, (VALUES (1), (3), (6), (12), (24)) v(n_h) GROUP BY 1 ORDER BY 1"),
    ("D. Signal and resolution", "D9", "Large jumps (8 or more bikes in one 10-minute step) by UTC hour (rebalancing hypothesis; no truck data)",
     f"SELECT hour(t) AS utc_hour, count(*) FILTER (WHERE b - pb >= 8) AS jumps_up, count(*) FILTER (WHERE pb - b >= 8) AS jumps_down "
     f"FROM pairs WHERE {G} GROUP BY 1 ORDER BY 1"),

    ("E. Weather", "E1", "Weather coverage",
     "SELECT count(*) AS runs, count(*) - count(temp_c) AS runs_missing_weather, count(DISTINCT weather_time) AS distinct_weather_timestamps, "
     "min(temp_c) AS min_temp_c, max(temp_c) AS max_temp_c, count(*) FILTER (WHERE precip_mm > 0) AS runs_with_rain, max(precip_mm) AS max_precip_mm, "
     "count(DISTINCT weather_code) AS distinct_weather_codes FROM rm"),
    ("E. Weather", "E2", "Weather by UTC day",
     "SELECT cast(snapshot_ts AS date) AS utc_day, min(temp_c) AS min_temp_c, max(temp_c) AS max_temp_c, "
     "count(*) FILTER (WHERE precip_mm > 0) AS runs_with_rain, round(max(precip_mm), 1) AS max_precip_mm FROM rm GROUP BY 1 ORDER BY 1"),

    ("F. Calendar coverage", "F1", "Complete UTC days by weekday (first partial day excluded)",
     "SELECT dayname(d) AS weekday, count(*) AS days_observed FROM (SELECT DISTINCT cast(snapshot_ts AS date) AS d FROM rm) "
     "WHERE d > (SELECT min(cast(snapshot_ts AS date)) FROM rm) GROUP BY 1 ORDER BY min(d)"),
]

# Reconciliation of our own dbt tables with the raw data (needs --dbt-db built from the SAME data root).
RECON_RAW = """
SELECT count(*) AS rows_, count(*) FILTER (WHERE inst AND rent AND b = 0) AS stockouts,
       count(*) FILTER (WHERE inst AND ret AND d = 0) AS blockouts, count(*) FILTER (WHERE inst) AS installed_rows
FROM pairs
"""
RECON_DBT = """
SELECT count(*) AS rows_, count(*) FILTER (WHERE is_stockout) AS stockouts,
       count(*) FILTER (WHERE is_blockout) AS blockouts, count(*) FILTER (WHERE is_service_eligible) AS installed_rows
FROM fct_station_snapshot
"""


def md_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_(no rows)_\n"

    def fmt(v):
        if isinstance(v, float):
            return "" if pd.isna(v) else f"{v:.4g}" if abs(v) < 1000 else f"{v:,.1f}"
        if isinstance(v, (pd.Timestamp, datetime)):
            return str(v)[:19]
        return "" if v is None or (not isinstance(v, str) and pd.isna(v)) else str(v)

    head = "| " + " | ".join(map(str, df.columns)) + " |\n"
    sep = "|" + "|".join(["---"] * len(df.columns)) + "|\n"
    body = "".join("| " + " | ".join(fmt(v) for v in row) + " |\n" for row in df.itertuples(index=False))
    return head + sep + body


def run(data: Path, out: Path, dbt_db: Path | None) -> dict:
    con = duckdb.connect()
    setup(con, data)
    lines = [
        "# Data integrity results (auto-generated)",
        "",
        f"Generated by `src/audit/run_audit.py` on `{data.as_posix()}` at {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC. "
        "Do not edit by hand; re-run the script. Interpretation lives in `docs/data_integrity_report.md`.",
        "",
    ]
    section = None
    results: dict[str, pd.DataFrame] = {}
    for sec, cid, title, sql in CHECKS:
        if sec != section:
            lines += [f"## {sec}", ""]
            section = sec
        df = con.sql(sql).df()
        results[cid] = df
        lines += [f"### {cid}. {title}", "", md_table(df)]
    if dbt_db is not None and dbt_db.exists():
        raw = con.sql(RECON_RAW).df()
        d = duckdb.connect(str(dbt_db), read_only=True)
        try:
            mod = d.sql(RECON_DBT).df()
        finally:
            d.close()
        rec = pd.concat([raw.assign(source="raw parquet"), mod.assign(source="dbt fct_station_snapshot")])
        rec = rec[["source", "rows_", "stockouts", "blockouts", "installed_rows"]]
        match = bool((raw.iloc[0] == mod.iloc[0]).all())
        results["G1"] = rec
        lines += ["## G. Our own models versus raw data", "",
                  f"### G1. Row and flag counts (match: **{match}**)", "", md_table(rec)]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--data", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--dbt-db", type=Path, default=None)
    a = ap.parse_args()
    run(a.data, a.out, a.dbt_db)
    print(f"wrote {a.out}")
