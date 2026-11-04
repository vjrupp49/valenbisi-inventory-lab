"""Evaluation harness: guards, bootstrap arithmetic and placebo on hand-made (SYNTHETIC) hourly data."""
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from forecast import evaluate  # noqa: E402
from forecast.metrics import brier  # noqa: E402
from test_forecast import _hourly  # noqa: E402


def _db(tmp_path, n_days):
    db = tmp_path / "x.duckdb"
    con = duckdb.connect(str(db))
    con.register("h", _hourly(n_days=n_days))
    con.execute("create table fct_station_hour as select *, true as is_service_eligible from h")
    con.close()
    return str(db)


def test_real_data_guard_blocks_short_history(tmp_path):
    assert evaluate.evaluate(_db(tmp_path, 8), tmp_path / "o.md", synthetic=False) == {}
    assert not (tmp_path / "o.md").exists()


def test_synthetic_run_produces_all_sections_and_labels_it(tmp_path):
    res = evaluate.evaluate(_db(tmp_path, 12), tmp_path / "o.md", min_train_days=4, n_boot=50, synthetic=True)
    text = (tmp_path / "o.md").read_text(encoding="utf-8")
    assert "SYNTHETIC DATA - NOT A REAL RESULT" in text
    assert {"overall", "skill", "per_day", "blocks", "placebo"} <= set(res)
    assert set(res["overall"]["model"]) == {"persistence", "station_mean", "station_state", "hour_of_week", "gbm"}
    plac = res["placebo"].set_index("check")["brier"]
    # The toy data is too small for the placebo to be informative (it only has 2 stations); just check it runs
    # and yields valid scores. Its meaning on the real data is judged in docs/forecast_findings.md.
    assert len(plac) == 3 and plac.between(0, 1).all()


def test_bootstrap_point_estimate_equals_pooled_brier():
    rng = np.random.default_rng(0)
    rows = []
    for m in ("gbm", "persistence"):
        for d in range(5):
            y = rng.integers(0, 2, 30)
            p = np.clip(rng.random(30), 0.05, 0.95)
            rows.append(pd.DataFrame({"model": m, "fold_date": d, "y": y, "p": p}))
    preds = pd.concat(rows, ignore_index=True)
    b = evaluate.day_block_bootstrap(preds, 200)
    g = preds[preds["model"] == "gbm"]
    assert b["brier"]["gbm"][0] == pytest.approx(brier(g["y"], g["p"]))
    lo, hi = b["brier"]["gbm"][1:]
    assert lo <= b["brier"]["gbm"][0] <= hi
