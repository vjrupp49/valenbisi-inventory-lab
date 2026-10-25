"""The service-level analysis must reproduce known answers on hand-made data (SYNTHETIC)."""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "analysis"))
sys.path.insert(0, str(ROOT / "tests"))

import service_level  # noqa: E402
from test_dbt_models import build_dbt, hand_made, pytestmark  # noqa: E402,F401  (pytestmark skips if dbt is missing)


def test_known_rates_and_exclusions(tmp_path):
    # Starts at Madrid midnight (23:00 UTC in January), three complete local days of 10-minute snapshots.
    start = datetime(2030, 1, 6, 23, 0, tzinfo=timezone.utc)
    n = 144 * 3
    cycle_a = [0, 0, 1, 2, 3, 4, 5, 4, 3, 2, 1, 2]           # 2 of every 12 snapshots are stockouts
    series = {"A": [cycle_a[k % 12] for k in range(n)], "B": [5] * n}   # B never changes -> stuck after 12 h
    status, meta, info = hand_made(series, start)
    build_dbt(tmp_path, status, meta, info)
    res = service_level.run(tmp_path / "t.duckdb", tmp_path / "out.md", tmp_path / "cache")

    s1 = res["S1"].set_index("day_type")["days"]
    assert s1.get("weekday", 0) + s1.get("weekend", 0) + s1.get("holiday", 0) == 3

    s2 = res["S2"].iloc[0]
    assert s2["installed_rows"] == 2 * n and s2["not_renting_rows"] == 0
    # B is flat from its first snapshot; snapshot 72 (12 h) onward is excluded: n - 72 rows. A is never flat that long.
    assert s2["renting_and_stuck_excluded"] == n - 72

    s3 = res["S3"].iloc[0]
    assert s3["stockout_raw"] == pytest.approx(round(2 * 36 / (2 * n), 4))        # 72 stockouts / 864 rows = 1/12
    # headline drops B's stuck (non-stockout) rows, so the rate rises
    assert s3["stockout_headline"] == pytest.approx(round(72 / (2 * n - (n - 72)), 4))
    assert s3["stockout_headline"] > s3["stockout_raw"]

    hourly = res["S5"].set_index(["day_type", "hour_of_day"])
    day_type = res["S1"]["day_type"].iloc[0]
    assert (tmp_path / "cache" / "hourly_summary.csv").exists()
    assert (tmp_path / "out.md").read_text(encoding="utf-8").startswith("# Service level results")
    assert not hourly.empty and day_type in {"weekday", "weekend", "holiday"}
