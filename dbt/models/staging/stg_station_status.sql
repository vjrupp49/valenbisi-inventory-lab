-- One row per station per snapshot, straight from the collector's parquet. Only renames/casts.
select
    cast(station_id as varchar)                 as station_id,
    snapshot_ts,
    feed_last_updated,
    cast(num_vehicles_available as integer)     as bikes,
    cast(num_docks_available as integer)        as docks,
    cast(num_vehicles_disabled as integer)      as bikes_disabled,
    cast(num_docks_disabled as integer)         as docks_disabled,
    coalesce(is_installed, false)               as is_installed,
    coalesce(is_renting, false)                 as is_renting,
    coalesce(is_returning, false)               as is_returning,
    last_reported
from read_parquet(
    '{{ var("data_root") }}/station_status/*/*.parquet',
    hive_partitioning = true, union_by_name = true
)
