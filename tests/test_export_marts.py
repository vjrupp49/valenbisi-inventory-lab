import duckdb
import pandas as pd

from export_marts import export


def test_export_writes_csvs_and_meta(tmp_path):
    db = tmp_path / "m.duckdb"
    con = duckdb.connect(str(db))
    for t in ("kpi_service_level", "seg_station_abc_xyz", "dim_station", "fct_run_health"):
        con.sql(f"create table {t} as select 1 as x")
    con.sql(
        "create table fct_station_snapshot as select * from (values "
        "(timestamptz '2030-01-07 10:00:00+00'), (timestamptz '2030-01-08 10:00:00+00')) t(snapshot_ts)"
    )
    con.close()
    meta = export(str(db), tmp_path / "out", synthetic=True)
    assert meta["n_days"] == 2 and meta["n_snapshots"] == 2 and meta["synthetic"] is True
    assert (tmp_path / "out" / "kpi_service_level.csv").exists()
    m = pd.read_csv(tmp_path / "out" / "meta.csv")
    assert m.loc[0, "first_ts"].startswith("2030-01-07 10:00:00")
