"""Snapshot the Valenbisi (Valencia bike-share) GBFS feeds into small Parquet files.

One run = one snapshot. Output layout (Hive-style partitions, DuckDB-friendly):

    <out>/station_status/dt=YYYY-MM-DD/ts=HHMMSS.parquet   one row per station
    <out>/run_meta/dt=YYYY-MM-DD/ts=HHMMSS.parquet         one row per run (health + weather)
    <out>/station_information/dt=YYYY-MM-DD/station_information.parquet   once per day

Design rules:
  * A failed fetch never crashes the run; it is recorded in run_meta so gaps are measurable.
  * Raw-ish and flat: no business logic here. Modeling happens downstream (dbt).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

GBFS_ROOT = "https://api.cyclocity.fr/contracts/valence/gbfs/v3"
STATUS_URL = f"{GBFS_ROOT}/station_status.json"
INFO_URL = f"{GBFS_ROOT}/station_information.json"
WEATHER_URL = (
    "https://api.open-meteo.com/v1/forecast?latitude=39.4699&longitude=-0.3763"
    "&current=temperature_2m,relative_humidity_2m,precipitation,rain,weather_code,wind_speed_10m"
    "&timezone=GMT"
)
# A real contact in the UA is good API etiquette.
USER_AGENT = "valenbisi-inventory-lab (portfolio project; github.com/vjrupp49/valenbisi-inventory-lab)"

STATUS_INT_COLS = [
    "num_vehicles_available",
    "num_docks_available",
    "num_vehicles_disabled",
    "num_docks_disabled",
    "bikes_mechanical",
    "bikes_other",
]
STATUS_BOOL_COLS = ["is_installed", "is_renting", "is_returning"]


# --------------------------------------------------------------------------- fetching
def get_json(url: str, retries: int = 3, timeout: int = 20) -> tuple[dict, int, int]:
    """GET json with retries. Returns (payload, http_status, latency_ms). Raises on final failure."""
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        t0 = time.monotonic()
        try:
            resp = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
            latency_ms = int((time.monotonic() - t0) * 1000)
            resp.raise_for_status()
            return resp.json(), resp.status_code, latency_ms
        except Exception as exc:  # noqa: BLE001 - we want to retry on anything transient
            last_exc = exc
            if attempt < retries:
                time.sleep(2**attempt)
    assert last_exc is not None
    raise last_exc


def _load(name: str, url: str, fixture_dir: Path | None) -> tuple[dict, int | None, int | None]:
    if fixture_dir is not None:
        with open(fixture_dir / f"{name}.json", encoding="utf-8") as fh:
            return json.load(fh), 200, 0
    return get_json(url)


# --------------------------------------------------------------------------- parsing
def _to_ts(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, errors="coerce")


def parse_status(payload: dict, snapshot_ts: datetime) -> pd.DataFrame:
    """Flatten a GBFS v3 station_status payload into one row per station."""
    rows = []
    for s in payload.get("data", {}).get("stations", []):
        counts = {
            v.get("vehicle_type_id"): v.get("count")
            for v in (s.get("vehicle_types_available") or [])
        }
        mech = counts.get("mechanical") or 0
        other = sum((c or 0) for k, c in counts.items() if k != "mechanical")
        rows.append(
            {
                "snapshot_ts": snapshot_ts,
                "feed_last_updated": payload.get("last_updated"),
                "station_id": str(s.get("station_id")),
                "num_vehicles_available": s.get("num_vehicles_available"),
                "num_docks_available": s.get("num_docks_available"),
                "num_vehicles_disabled": s.get("num_vehicles_disabled"),
                "num_docks_disabled": s.get("num_docks_disabled"),
                "is_installed": s.get("is_installed"),
                "is_renting": s.get("is_renting"),
                "is_returning": s.get("is_returning"),
                "last_reported": s.get("last_reported"),
                "bikes_mechanical": mech,
                "bikes_other": other,
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["snapshot_ts"] = _to_ts(df["snapshot_ts"])
    df["feed_last_updated"] = _to_ts(df["feed_last_updated"])
    df["last_reported"] = _to_ts(df["last_reported"])
    for col in STATUS_INT_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    for col in STATUS_BOOL_COLS:
        df[col] = df[col].astype("boolean")
    return df


def _localized(value):
    """GBFS v3 names are lists like [{"text": "...", "language": "es"}]; v2 used plain strings."""
    if isinstance(value, list) and value:
        first = value[0]
        return first.get("text") if isinstance(first, dict) else str(first)
    return value


def parse_info(payload: dict, snapshot_ts: datetime) -> pd.DataFrame:
    rows = []
    for s in payload.get("data", {}).get("stations", []):
        rows.append(
            {
                "snapshot_ts": snapshot_ts,
                "station_id": str(s.get("station_id")),
                "name": _localized(s.get("name")),
                "lat": s.get("lat"),
                "lon": s.get("lon"),
                "capacity": s.get("capacity"),
                "address": _localized(s.get("address")),
                "raw_json": json.dumps(s, ensure_ascii=False, sort_keys=True),
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["snapshot_ts"] = _to_ts(df["snapshot_ts"])
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df["capacity"] = pd.to_numeric(df["capacity"], errors="coerce").astype("Int64")
    return df


def parse_weather(payload: dict) -> dict:
    cur = payload.get("current") or {}
    return {
        "weather_time": cur.get("time"),
        "temp_c": cur.get("temperature_2m"),
        "humidity_pct": cur.get("relative_humidity_2m"),
        "precip_mm": cur.get("precipitation"),
        "rain_mm": cur.get("rain"),
        "weather_code": cur.get("weather_code"),
        "wind_kmh": cur.get("wind_speed_10m"),
    }


def build_run_meta(
    snapshot_ts: datetime,
    status_df: pd.DataFrame,
    http_status: int | None,
    latency_ms: int | None,
    error: str | None,
    weather: dict,
    weather_error: str | None,
) -> pd.DataFrame:
    """One health/context row per run. This is what makes data gaps measurable later."""
    meta: dict = {
        "snapshot_ts": snapshot_ts,
        "ok": error is None,
        "error": error,
        "http_status": http_status,
        "latency_ms": latency_ms,
        "n_stations": 0,
        "n_installed": 0,
        "feed_last_updated": None,
        "feed_age_s": None,
        "max_last_reported": None,
        "n_stale_1h": 0,
        "weather_error": weather_error,
    }
    if not status_df.empty:
        feed_updated = status_df["feed_last_updated"].iloc[0]
        installed = status_df[status_df["is_installed"].fillna(False).astype(bool)]
        age_s = (snapshot_ts - feed_updated).total_seconds() if pd.notna(feed_updated) else None
        stale_cutoff = pd.Timestamp(snapshot_ts) - pd.Timedelta(hours=1)
        meta.update(
            {
                "n_stations": int(len(status_df)),
                "n_installed": int(len(installed)),
                "feed_last_updated": feed_updated,
                "feed_age_s": age_s,
                "max_last_reported": status_df["last_reported"].max(),
                "n_stale_1h": int((installed["last_reported"] < stale_cutoff).sum()),
            }
        )
    meta.update(weather)
    df = pd.DataFrame([meta])
    for col in ("snapshot_ts", "feed_last_updated", "max_last_reported"):
        df[col] = _to_ts(df[col])
    return df


# --------------------------------------------------------------------------- output
def write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False, compression="zstd")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--out", required=True, type=Path, help="output root (the data branch checkout)")
    parser.add_argument("--fixture-dir", type=Path, default=None, help="read JSON fixtures instead of the network")
    args = parser.parse_args(argv)

    snapshot_ts = datetime.now(timezone.utc).replace(microsecond=0)
    dt = snapshot_ts.strftime("%Y-%m-%d")
    ts = snapshot_ts.strftime("%H%M%S")
    out: Path = args.out

    # 1) station status (the core feed)
    status_df = pd.DataFrame()
    http_status = latency_ms = None
    error = None
    try:
        payload, http_status, latency_ms = _load("station_status", STATUS_URL, args.fixture_dir)
        status_df = parse_status(payload, snapshot_ts)
        if status_df.empty:
            error = "empty station list"
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"[:500]

    # 2) weather (optional; never fatal)
    weather: dict = {}
    weather_error = None
    try:
        wpayload, _, _ = _load("weather", WEATHER_URL, args.fixture_dir)
        weather = parse_weather(wpayload)
    except Exception as exc:  # noqa: BLE001
        weather_error = f"{type(exc).__name__}: {exc}"[:500]

    # 3) station information, once per day
    info_path = out / "station_information" / f"dt={dt}" / "station_information.parquet"
    if not info_path.exists():
        try:
            ipayload, _, _ = _load("station_information", INFO_URL, args.fixture_dir)
            info_df = parse_info(ipayload, snapshot_ts)
            if not info_df.empty:
                write_parquet(info_df, info_path)
        except Exception as exc:  # noqa: BLE001
            print(f"station_information fetch failed: {exc}", file=sys.stderr)

    # 4) write outputs
    meta_df = build_run_meta(snapshot_ts, status_df, http_status, latency_ms, error, weather, weather_error)
    write_parquet(meta_df, out / "run_meta" / f"dt={dt}" / f"ts={ts}.parquet")
    if not status_df.empty:
        write_parquet(status_df, out / "station_status" / f"dt={dt}" / f"ts={ts}.parquet")

    print(
        f"{snapshot_ts.isoformat()} ok={error is None} stations={len(status_df)} "
        f"http={http_status} latency_ms={latency_ms} error={error}"
    )
    # Exit 0 even on fetch errors so a flaky upstream doesn't spam failure emails;
    # the failure is recorded in run_meta instead.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
