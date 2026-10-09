import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import ingest  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
NOW = datetime(2099, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _load(name):
    with open(FIX / f"{name}.json", encoding="utf-8") as fh:
        return json.load(fh)


def test_parse_status_shape_and_types():
    df = ingest.parse_status(_load("station_status"), NOW)
    assert len(df) == 3
    assert df["station_id"].tolist() == ["1", "2", "16"]
    assert str(df["num_vehicles_available"].dtype) == "Int64"
    assert str(df["is_installed"].dtype) == "boolean"
    assert df["last_reported"].dt.tz is not None


def test_vehicle_type_split():
    df = ingest.parse_status(_load("station_status"), NOW).set_index("station_id")
    assert df.loc["2", "bikes_mechanical"] == 3
    assert df.loc["2", "bikes_other"] == 1


def test_parse_info_handles_v3_and_plain_names():
    df = ingest.parse_info(_load("station_information"), NOW).set_index("station_id")
    assert df.loc["1", "name"] == "01_PLAZA TEST"
    assert df.loc["2", "name"] == "02_PLAIN STRING NAME"
    assert df.loc["1", "capacity"] == 25


def test_run_meta_counts_stale_installed_stations_only():
    status = ingest.parse_status(_load("station_status"), NOW)
    meta = ingest.build_run_meta(NOW, status, 200, 120, None, ingest.parse_weather(_load("weather")), None)
    row = meta.iloc[0]
    assert bool(row["ok"]) is True
    assert row["n_stations"] == 3
    assert row["n_installed"] == 2
    # station 2 last reported ~10.8 h ago -> stale; station 1 fresh; station 16 not installed -> ignored
    assert row["n_stale_1h"] == 1
    assert abs(row["feed_age_s"] - 30) < 1
    assert row["temp_c"] == 18.4


def test_run_meta_records_failure():
    meta = ingest.build_run_meta(NOW, pd.DataFrame(), None, None, "Timeout: boom", {}, None)
    row = meta.iloc[0]
    assert bool(row["ok"]) is False
    assert row["error"] == "Timeout: boom"
    assert row["n_stations"] == 0


def test_end_to_end_with_fixtures(tmp_path):
    rc = ingest.main(["--out", str(tmp_path), "--fixture-dir", str(FIX)])
    assert rc == 0
    assert list(tmp_path.glob("station_status/dt=*/ts=*.parquet"))
    assert list(tmp_path.glob("run_meta/dt=*/ts=*.parquet"))
    assert list(tmp_path.glob("station_information/dt=*/station_information.parquet"))
