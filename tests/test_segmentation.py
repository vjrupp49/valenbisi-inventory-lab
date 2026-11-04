"""Segmentation logic on hand-made daily activity (SYNTHETIC). Mirrors dbt/models/marts/seg_station_abc_xyz.sql."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "analysis"))

from segmentation_stability import agreement, classify  # noqa: E402


def daily(values: dict[str, list[float]]) -> pd.DataFrame:
    rows = [(sid, f"2030-01-{d + 1:02d}", v) for sid, vs in values.items() for d, v in enumerate(vs)]
    return pd.DataFrame(rows, columns=["station_id", "local_date", "daily_activity"])


def test_abc_boundaries_and_xyz():
    d = daily({
        "s1": [100, 100, 100, 100],        # 100 of 120 total activity -> A (nothing before it), perfectly steady -> X
        "s2": [10, 20, 10, 20],            # mean 15, cum_before 100/120 = 0.83 >= 0.80 -> B ; cv ~0.39 -> X
        "s3": [0, 0, 0, 20],               # mean 5, cum_before 115/120 = 0.958 >= 0.95 -> C ; cv 2 -> Z
        "s4": [0, 0, 0, 0],                # no activity -> C and n/a
    })
    c = classify(d).set_index("station_id")
    assert c.loc["s1", ["abc_class", "xyz_class"]].tolist() == ["A", "X"]
    assert c.loc["s2", "abc_class"] == "B" and c.loc["s2", "xyz_class"] == "X"
    assert c.loc["s3", ["abc_class", "xyz_class"]].tolist() == ["C", "Z"]
    assert c.loc["s4", ["abc_class", "xyz_class"]].tolist() == ["C", "n/a"]


def test_order_of_days_does_not_matter_and_ties_are_deterministic():
    d = daily({"a": [5, 5, 5], "b": [5, 5, 5], "c": [1, 1, 1]})
    c1 = classify(d).set_index("station_id")["abc_class"]
    c2 = classify(d.sample(frac=1, random_state=1)).set_index("station_id")["abc_class"]
    assert c1.equals(c2.reindex(c1.index))


def test_all_zero_activity_is_all_c():
    c = classify(daily({"a": [0, 0], "b": [0, 0]}))
    assert set(c["abc_class"]) == {"C"} and set(c["xyz_class"]) == {"n/a"}


def test_agreement_metrics():
    a = pd.Series(list("AABBCC"), index=list("123456"))
    assert agreement(a, a)["same_class_share"] == 1.0 and agreement(a, a)["cohens_kappa"] == 1.0
    b = a.copy()
    b["1"] = "C"
    assert agreement(a, b)["same_class_share"] == pytest.approx(5 / 6, abs=1e-3)
