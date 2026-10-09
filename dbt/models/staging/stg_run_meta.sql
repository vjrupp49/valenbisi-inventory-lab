-- One row per collector run, including failed runs (those have no station rows).
select
    snapshot_ts,
    ok,
    error,
    http_status,
    latency_ms,
    n_stations,
    n_installed,
    feed_last_updated,
    feed_age_s,
    max_last_reported,
    n_stale_1h,
    temp_c,
    precip_mm,
    wind_kmh,
    weather_code
from read_parquet(
    '{{ var("data_root") }}/run_meta/*/*.parquet',
    hive_partitioning = true, union_by_name = true
)
