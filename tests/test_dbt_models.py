"""Runs the dbt project against SYNTHETIC / hand-made data and checks the modeled logic against the raw frames.

Skipped if dbt is not installed (the plain `pip install -r requirements.txt` environment).
"""
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import synth  # noqa: E402

DBT = shutil.which("dbt") or str(Path(sys.executable).parent / "dbt")
pytestmark = pytest.mark.skipif(
    not (shutil.which("dbt") or (Path(sys.executable).parent / "dbt.exe").exists()
         or (Path(sys.executable).parent / "dbt").exists()),
    reason="dbt not installed",
)


def build_dbt(tmp: Path, status, meta, info):
    """Write the frames in the collector's layout, run `dbt build`, return a read-only DuckDB connection."""
    data = tmp / "data"
    synth.write_layout(status, meta, info, data, compact=True)
    db = tmp / "t.duckdb"
    profiles = tmp / "profiles.yml"
    profiles.write_text(
        "valenbisi:\n  target: dev\n  outputs:\n    dev:\n      type: duckdb\n"
        f"      path: '{db.as_posix()}'\n      settings:\n        TimeZone: UTC\n"
    )
    res = subprocess.run(
        [DBT, "build", "--project-dir", str(ROOT / "dbt"), "--profiles-dir", str(tmp),
         "--target-path", str(tmp / "target"), "--log-path", str(tmp / "logs"),
         "--vars", f"{{data_root: '{data.as_posix()}'}}"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stdout[-3000:] + res.stderr[-1000:]
    con = duckdb.connect(str(db), read_only=True)
    con.execute("SET TimeZone='UTC'")
    return con


def hand_made(series: dict, start: datetime, step_min=10, capacity=10, installed=True, renting=True, cap_by_day=None):
    """Frames for stations with given bike-count series (dict station_id -> list). last_reported never moves."""
    n = len(next(iter(series.values())))
    times = [start + timedelta(minutes=step_min * k) for k in range(n)]
    rows = []
    for sid, ser in series.items():
        for t, b in zip(times, ser):
            cap = (cap_by_day or {}).get(t.date().isoformat(), capacity)
            rows.append({
                "snapshot_ts": t, "feed_last_updated": t - timedelta(seconds=5), "station_id": sid,
                "num_vehicles_available": b, "num_docks_available": cap - b, "num_vehicles_disabled": 0,
                "num_docks_disabled": 0, "is_installed": installed, "is_renting": renting, "is_returning": installed,
                "last_reported": start - timedelta(days=2), "bikes_mechanical": b, "bikes_other": 0,
            })
    status = pd.DataFrame(rows)
    meta = pd.DataFrame({"snapshot_ts": times, "ok": True, "error": None, "http_status": 200, "latency_ms": 1,
                         "n_stations": len(series), "n_installed": len(series), "feed_last_updated": times,
                         "feed_age_s": 5.0, "max_last_reported": times, "n_stale_1h": 0, "weather_error": None,
                         "weather_time": "x", "temp_c": 15.0, "humidity_pct": 50, "precip_mm": 0.0, "rain_mm": 0.0,
                         "weather_code": 0, "wind_kmh": 1.0})
    days = sorted({t.date() for t in times})
    info = pd.concat([pd.DataFrame({
        "snapshot_ts": datetime(d.year, d.month, d.day, 0, 1, tzinfo=timezone.utc), "station_id": list(series),
        "name": "n", "lat": 39.4, "lon": -0.3,
        "capacity": (cap_by_day or {}).get(d.isoformat(), capacity), "address": "x", "raw_json": "{}"})
        for d in days], ignore_index=True)
    for df, cols in ((status, ["snapshot_ts", "feed_last_updated", "last_reported"]),
                     (meta, ["snapshot_ts", "feed_last_updated", "max_last_reported"]), (info, ["snapshot_ts"])):
        for c in cols:
            df[c] = pd.to_datetime(df[c], utc=True)
    for c in ("num_vehicles_available", "num_docks_available", "num_vehicles_disabled", "num_docks_disabled",
              "bikes_mechanical", "bikes_other"):
        status[c] = status[c].astype("Int64")
    for c in ("is_installed", "is_renting", "is_returning"):
        status[c] = status[c].astype("boolean")
    info["capacity"] = info["capacity"].astype("Int64")
    meta["error"] = meta["error"].astype("object")
    meta["weather_error"] = meta["weather_error"].astype("object")
    return status, meta, info


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("dbt_run")
    status, meta, info = synth.generate(n_stations=8, n_days=4, seed=11)
    return status, build_dbt(tmp, status, meta, info)


def test_snapshot_rowcount_matches_raw(built):
    status, con = built
    assert con.execute("select count(*) from fct_station_snapshot").fetchone()[0] == len(status)


def test_stockout_flag_matches_definition(built):
    status, con = built
    expected = int(((status["num_vehicles_available"] == 0) & status["is_installed"]).sum())
    got = con.execute("select count(*) from fct_station_snapshot where is_stockout").fetchone()[0]
    assert got == expected


def test_not_installed_station_excluded_from_service_metrics(built):
    _, con = built
    assert con.execute("select count(*) from kpi_service_level where station_id = '107'").fetchone()[0] == 0
    assert con.execute("select count(*) from seg_station_abc_xyz where station_id = '107'").fetchone()[0] == 0


def test_activity_null_across_gaps(built):
    _, con = built
    bad = con.execute(
        """select count(*) from (
             select snapshot_ts - lag(snapshot_ts) over (partition by station_id order by snapshot_ts) as g, activity
             from fct_station_snapshot) where g > interval 30 minutes and activity is not null"""
    ).fetchone()[0]
    assert bad == 0


def test_segmentation_logic(built):
    _, con = built
    rows = con.execute(
        "select abc_class, mean_daily_activity from seg_station_abc_xyz where abc_class <> 'n/a' "
        "order by mean_daily_activity desc"
    ).fetchall()
    classes = [r[0] for r in rows]
    assert classes == sorted(classes), "A stations must be at least as active as B, B as C"
    assert classes[0] == "A"
    total = sum(r[1] for r in rows)
    a_total = sum(r[1] for r in rows if r[0] == "A")
    # A is the smallest set whose running total first reaches the 80 % cutoff, so it covers >= 80 %
    assert a_total / total >= 0.80


def test_everything_provisional_with_few_days(built):
    _, con = built
    assert con.execute("select bool_and(is_provisional) from seg_station_abc_xyz").fetchone()[0]
    assert con.execute("select bool_and(is_provisional) from kpi_service_level").fetchone()[0]


def test_stuck_rule_flags_at_6h_and_excludes_at_12h(tmp_path):
    """Station S sits at 0 bikes for 20 h; station M moves every snapshot. last_reported never moves for either,
    which must NOT matter."""
    n = 6 * 20 + 1
    start = datetime(2030, 1, 7, 0, 0, tzinfo=timezone.utc)
    series = {"S": [0] * n, "M": [(k % 5) + 1 for k in range(n)]}
    con = build_dbt(tmp_path, *hand_made(series, start))
    s = con.execute(
        "select flat_hours, is_stuck, is_stuck_excluded, is_stockout, is_stockout_eligible from fct_station_snapshot "
        "where station_id = 'S' order by snapshot_ts"
    ).fetchall()
    assert not s[0][1] and s[0][3] and s[0][4]                     # first snapshot: nothing known yet
    assert not s[35][1] and s[36][1]                               # 36 snapshots later = 6.0 h  -> stuck
    assert not s[71][2] and s[72][2]                               # 12.0 h -> excluded
    assert s[72][3] and not s[72][4]                               # still a raw stockout, but not eligible
    m = con.execute("select max(flat_hours), bool_or(is_stuck) from fct_station_snapshot where station_id = 'M'").fetchone()
    assert m[0] <= 10 / 60 + 1e-9 and not m[1]


def test_headline_rate_excludes_not_renting(tmp_path):
    start = datetime(2030, 1, 7, 0, 0, tzinfo=timezone.utc)
    status, meta, info = hand_made({"A": [0] * 100}, start)
    # not-renting spell for the first 40 snapshots
    status.loc[status.index[:40], "is_renting"] = False
    con = build_dbt(tmp_path, status, meta, info)
    r = con.execute(
        "select sum(n_not_renting_rows), sum(n_stockout_eligible), round(avg(stockout_rate_raw), 4) from kpi_service_level"
    ).fetchone()
    assert r[0] == 40
    # Renting rows are snapshots 40..99 (60 rows, every one a raw stockout). The count is flat from the start, so
    # snapshot 72 reaches 12 h and is excluded: only snapshots 40..71 (32 rows) are eligible for the headline rate.
    assert r[1] == 32 and r[2] == 1.0


@pytest.mark.parametrize("start,dst_day,expected_hours", [
    (datetime(2030, 10, 26, 12, 0, tzinfo=timezone.utc), "2030-10-27", 25),   # clocks go back -> 25-hour local day
    (datetime(2030, 3, 30, 12, 0, tzinfo=timezone.utc), "2030-03-31", 23),    # clocks go forward -> 23-hour local day
])
def test_hourly_grain_survives_clock_changes(tmp_path, start, dst_day, expected_hours):
    n = 6 * 24 * 3
    series = {"X": [(k % 7) + 1 for k in range(n)]}
    con = build_dbt(tmp_path, *hand_made(series, start))
    got = con.execute(
        f"select count(*), count(distinct hour_utc) from fct_station_hour where local_date = date '{dst_day}'"
    ).fetchone()
    assert got == (expected_hours, expected_hours)
    assert con.execute("select count(*) - count(distinct station_hour_key) from fct_station_hour").fetchone()[0] == 0


def test_capacity_is_looked_up_as_of_the_snapshot_date(tmp_path):
    start = datetime(2030, 1, 7, 12, 0, tzinfo=timezone.utc)
    n = 6 * 36   # runs across midnight into the next day
    status, meta, info = hand_made({"A": [3] * n}, start, cap_by_day={"2030-01-07": 20, "2030-01-08": 16})
    con = build_dbt(tmp_path, status, meta, info)
    got = dict(con.execute(
        "select cast(snapshot_ts as date), min(capacity) from fct_station_snapshot group by 1").fetchall())
    assert got[datetime(2030, 1, 7).date()] == 20 and got[datetime(2030, 1, 8).date()] == 16
    assert con.execute("select max(capacity) from fct_station_snapshot where snapshot_ts >= timestamptz '2030-01-08 00:30:00+00'"
                       ).fetchone()[0] == 16


def test_holiday_flag_from_seed(tmp_path):
    start = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)   # Fiesta Nacional (Monday)
    series = {"A": [(k % 4) + 1 for k in range(6 * 36)]}         # runs into Oct 13
    con = build_dbt(tmp_path, *hand_made(series, start))
    got = dict(con.execute("select local_date, bool_or(is_holiday) from fct_station_snapshot group by 1").fetchall())
    assert got[datetime(2026, 10, 12).date()] is True and got[datetime(2026, 10, 13).date()] is False
