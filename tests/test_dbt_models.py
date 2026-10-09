"""Runs the dbt project against SYNTHETIC data and checks the modeled logic against the raw frames.

Skipped if dbt is not installed (the plain `pip install -r requirements.txt` environment).
"""
import shutil
import subprocess
import sys
from pathlib import Path

import duckdb
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


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("dbt_run")
    data = tmp / "data"
    status, meta, info = synth.generate(n_stations=8, n_days=4, seed=11)
    synth.write_layout(status, meta, info, data, compact=True)
    db = tmp / "t.duckdb"
    profiles = tmp / "profiles.yml"
    profiles.write_text(
        f"valenbisi:\n  target: dev\n  outputs:\n    dev:\n      type: duckdb\n      path: '{db.as_posix()}'\n"
    )
    res = subprocess.run(
        [DBT, "build", "--project-dir", str(ROOT / "dbt"), "--profiles-dir", str(tmp),
         "--target-path", str(tmp / "target"), "--log-path", str(tmp / "logs"),
         "--vars", f"{{data_root: '{data.as_posix()}'}}"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stdout[-3000:] + res.stderr[-1000:]
    return status, duckdb.connect(str(db), read_only=True)


def test_snapshot_rowcount_matches_raw(built):
    status, con = built
    assert con.sql("select count(*) from fct_station_snapshot").fetchone()[0] == len(status)


def test_stockout_flag_matches_definition(built):
    status, con = built
    expected = int(((status["num_vehicles_available"] == 0) & status["is_installed"]).sum())
    got = con.sql("select count(*) from fct_station_snapshot where is_stockout").fetchone()[0]
    assert got == expected


def test_not_installed_station_excluded_from_service_metrics(built):
    _, con = built
    assert con.sql("select count(*) from kpi_service_level where station_id = '107'").fetchone()[0] == 0
    assert con.sql("select count(*) from seg_station_abc_xyz where station_id = '107'").fetchone()[0] == 0


def test_activity_null_across_gaps(built):
    _, con = built
    bad = con.sql(
        """select count(*) from (
             select snapshot_ts - lag(snapshot_ts) over (partition by station_id order by snapshot_ts) as g, activity
             from fct_station_snapshot) where g > interval 30 minutes and activity is not null"""
    ).fetchone()[0]
    assert bad == 0


def test_segmentation_logic(built):
    _, con = built
    rows = con.sql(
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
    assert con.sql("select bool_and(is_provisional) from seg_station_abc_xyz").fetchone()[0]
    assert con.sql("select bool_and(is_provisional) from kpi_service_level").fetchone()[0]
