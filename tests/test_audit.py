"""The audit script must give the right answers on data where we know them. Hand-made / SYNTHETIC data only."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "audit"))

import run_audit  # noqa: E402
import synth  # noqa: E402

T0 = datetime(2030, 1, 7, 0, 0, tzinfo=timezone.utc)


def _tiny(tmp_path):
    """Station A: bikes 3,3,0,0,0,5 (one 3-snapshot stockout, 2 count changes). Station B never changes.
    last_reported never moves for either, so 'count changed but last_reported did not' must be 2 for A."""
    times = [T0 + timedelta(minutes=10 * k) for k in range(6)]
    rows = []
    for sid, series in (("A", [3, 3, 0, 0, 0, 5]), ("B", [4] * 6)):
        for t, b in zip(times, series):
            rows.append({
                "snapshot_ts": t, "feed_last_updated": t - timedelta(seconds=5), "station_id": sid,
                "num_vehicles_available": b, "num_docks_available": 10 - b, "num_vehicles_disabled": 0,
                "num_docks_disabled": 0, "is_installed": True, "is_renting": True, "is_returning": True,
                "last_reported": T0 - timedelta(days=1), "bikes_mechanical": b, "bikes_other": 0,
            })
    status = pd.DataFrame(rows)
    meta = pd.DataFrame({"snapshot_ts": times, "ok": True, "temp_c": 15.0, "precip_mm": 0.0, "weather_time": "x", "weather_code": 0, "feed_age_s": 5.0})
    info = pd.DataFrame({"snapshot_ts": T0, "station_id": ["A", "B"], "name": ["a", "b"], "lat": 39.4, "lon": -0.3,
                         "capacity": 10, "address": "x"})
    for df, cols in ((status, ["snapshot_ts", "feed_last_updated", "last_reported"]), (meta, ["snapshot_ts"]), (info, ["snapshot_ts"])):
        for c in cols:
            df[c] = pd.to_datetime(df[c], utc=True)
    synth.write_layout(status, meta, info, tmp_path / "data")
    return tmp_path / "data"


def test_known_answers(tmp_path):
    data = _tiny(tmp_path)
    res = run_audit.run(data, tmp_path / "out.md", None)
    assert res["A1"].loc[0, "snapshots"] == 6 and res["A1"].loc[0, "stations"] == 2
    assert res["A6"].loc[0, "duplicate_station_snapshots"] == 0
    d5 = res["D5"].loc[0]
    assert d5["episodes"] == 1 and d5["median_snapshots"] == 3 and d5["one_snapshot_only"] == 0
    c3 = res["C3"].set_index(["bike_count_changed", "last_reported_changed"])["station_intervals"]
    assert c3[(False, False)] == 8 and c3[(True, False)] == 2 and (True, True) not in c3.index
    d1 = res["D1"].loc[0]
    assert d1["stations"] == 2 and d1["never_changed"] == 1
    assert res["D4"].loc[0, "stations_with_any_stockout"] == 1
    assert res["A3"].loc[0, "over_15min"] == 0
    # B2: bikes + docks equals capacity everywhere in this data
    assert res["B2"].loc[0, "equals_capacity"] == res["B2"].loc[0, "n"]
    assert (tmp_path / "out.md").read_text(encoding="utf-8").startswith("# Data integrity results")


def test_detects_gaps_and_flags_on_synthetic(tmp_path):
    status, meta, info = synth.generate(n_stations=6, n_days=3, seed=5)  # includes a built-in 2 h outage
    data = tmp_path / "data"
    synth.write_layout(status, meta, info, data, compact=True)
    res = run_audit.run(data, tmp_path / "out.md", None)
    assert len(res["A3b"]) >= 1 and res["A3b"]["gap_min"].max() >= 120
    assert res["B1"]["is_installed"].tolist().count(False) == 1  # the synthetic not-installed station
    assert res["A6"].loc[0, "folder_date_mismatch"] == 0


def test_dst_check_finds_the_repeated_madrid_hour(tmp_path):
    data = _tiny(tmp_path)
    res = run_audit.run(data, tmp_path / "out.md", None)
    # 2026-10-25: clocks go back, so Madrid hour 2 happens twice
    assert res["A8"]["madrid_hour"].tolist() == [2]
