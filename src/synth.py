"""SYNTHETIC data generator. Everything produced here is made up.

Purpose: tests, the dbt CI sample, and developing the forecast/simulate scaffolds before enough real
history exists. Output mimics the layout and dtypes written by src/ingest.py so the same models run
on both. No result computed from this data may be reported as a real finding.

    python src/synth.py --out dbt/sample_data --stations 12 --days 3 --seed 7
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ingest import write_parquet

START = datetime(2030, 1, 7, 0, 0, tzinfo=timezone.utc)  # a Monday, in the future on purpose
STEP_MIN = 10  # matches the collector's nominal cadence


def generate(n_stations: int = 12, n_days: int = 3, seed: int = 7, start: datetime = START,
             skip_prob: float = 0.08, outage_hours: tuple[int, int] | None = (30, 32)):
    """Return (status, meta, info) DataFrames. Deterministic for a given seed."""
    rng = np.random.default_rng(seed)
    ids = [str(100 + i) for i in range(n_stations)]
    capacity = rng.integers(14, 31, n_stations)
    popularity = rng.uniform(0.3, 3.0, n_stations)   # scales how much a station moves
    commute_dir = rng.choice([-1, 1], n_stations)     # drains in the morning vs fills
    installed = np.ones(n_stations, dtype=bool)
    installed[-1] = False                              # one not-installed station

    grid = [start + timedelta(minutes=STEP_MIN * k) for k in range(n_days * 24 * 60 // STEP_MIN)]
    keep = rng.random(len(grid)) > skip_prob           # cron skips
    if outage_hours:
        lo, hi = outage_hours
        for k, t in enumerate(grid):
            if lo <= (t - start).total_seconds() / 3600 < hi:
                keep[k] = False
    keep[0] = True

    bikes = (capacity * rng.uniform(0.2, 0.8, n_stations)).astype(int)
    last_rep = np.array([start - timedelta(hours=int(h)) for h in rng.integers(1, 48, n_stations)], dtype=object)
    status_rows, meta_rows = [], []
    for k, t in enumerate(grid):
        hour = t.hour + t.minute / 60
        # morning (7-10) and evening (17-20) pulses push bikes out of / into stations
        pulse = np.exp(-((hour - 8.5) ** 2) / 2) - np.exp(-((hour - 18.5) ** 2) / 2)
        drift = commute_dir * pulse * popularity * 0.6
        night = 0.15 if (hour < 5) else 1.0
        moves = rng.poisson(popularity * night * 0.5, n_stations) * rng.choice([-1, 1], n_stations)
        new = np.clip(np.round(bikes + drift + moves).astype(int), 0, capacity)
        changed = (new != bikes) & installed
        bikes = new
        for i in np.where(changed)[0]:
            last_rep[i] = t - timedelta(seconds=int(rng.integers(5, 600)))
        if not keep[k]:
            continue
        feed_updated = t - timedelta(seconds=float(rng.uniform(5, 60)))
        n_stale = 0
        for i, sid in enumerate(ids):
            if installed[i] and last_rep[i] < t - timedelta(hours=1):
                n_stale += 1
            status_rows.append({
                "snapshot_ts": t, "feed_last_updated": feed_updated, "station_id": sid,
                "num_vehicles_available": int(bikes[i]),
                "num_docks_available": int(capacity[i] - bikes[i]),
                "num_vehicles_disabled": 0, "num_docks_disabled": 0,
                "is_installed": bool(installed[i]), "is_renting": bool(installed[i]),
                "is_returning": bool(installed[i]), "last_reported": last_rep[i],
                "bikes_mechanical": int(bikes[i]), "bikes_other": 0,
            })
        meta_rows.append({
            "snapshot_ts": t, "ok": True, "error": None, "http_status": 200, "latency_ms": 300,
            "n_stations": n_stations, "n_installed": int(installed.sum()),
            "feed_last_updated": feed_updated, "feed_age_s": (t - feed_updated).total_seconds(),
            "max_last_reported": max(last_rep), "n_stale_1h": n_stale, "weather_error": None,
            "weather_time": t.strftime("%Y-%m-%dT%H:%M"), "temp_c": 15.0, "humidity_pct": 60,
            "precip_mm": 0.0, "rain_mm": 0.0, "weather_code": 0, "wind_kmh": 5.0,
        })
    status = pd.DataFrame(status_rows)
    meta = pd.DataFrame(meta_rows)
    info = pd.DataFrame({
        "snapshot_ts": start, "station_id": ids, "name": [f"SYNTH {s}" for s in ids],
        "lat": 39.47 + rng.normal(0, 0.01, n_stations), "lon": -0.376 + rng.normal(0, 0.01, n_stations),
        "capacity": capacity, "address": [f"Synthetic st {s}" for s in ids], "raw_json": "{}",
    })
    for col in ("snapshot_ts", "feed_last_updated", "last_reported"):
        status[col] = pd.to_datetime(status[col], utc=True)
    for col in ("snapshot_ts", "feed_last_updated", "max_last_reported"):
        meta[col] = pd.to_datetime(meta[col], utc=True)
    info["snapshot_ts"] = pd.to_datetime(info["snapshot_ts"], utc=True)
    for col in ("num_vehicles_available", "num_docks_available", "num_vehicles_disabled",
                "num_docks_disabled", "bikes_mechanical", "bikes_other"):
        status[col] = status[col].astype("Int64")
    for col in ("is_installed", "is_renting", "is_returning"):
        status[col] = status[col].astype("boolean")
    info["capacity"] = info["capacity"].astype("Int64")
    meta["error"] = meta["error"].astype("object")
    meta["weather_error"] = meta["weather_error"].astype("object")
    return status, meta, info


def write_layout(status, meta, info, out: Path, compact: bool = False) -> None:
    """Write the three tables in the same Hive layout the collector uses.

    compact=True writes one file per day (ts=000000.parquet) instead of one per snapshot, which
    keeps a committed sample small. The models glob the files, so they cannot tell the difference.
    """
    def _write(df, table):
        key = df["snapshot_ts"].dt.strftime("%Y-%m-%d") if compact else df["snapshot_ts"]
        for k, grp in df.groupby(key):
            if compact:
                dt, ts = k, "000000"
            else:
                dt, ts = k.strftime("%Y-%m-%d"), k.strftime("%H%M%S")
            write_parquet(grp, out / table / f"dt={dt}" / f"ts={ts}.parquet")

    _write(status, "station_status")
    _write(meta, "run_meta")
    for dt in sorted({t.strftime("%Y-%m-%d") for t in status["snapshot_ts"]}):
        write_parquet(info, out / "station_information" / f"dt={dt}" / "station_information.parquet")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--stations", type=int, default=12)
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--compact", action="store_true", help="one file per day")
    a = ap.parse_args()
    s, m, i = generate(a.stations, a.days, a.seed)
    write_layout(s, m, i, a.out, a.compact)
    print(f"SYNTHETIC data written to {a.out}: {len(s)} status rows, {len(m)} runs")
