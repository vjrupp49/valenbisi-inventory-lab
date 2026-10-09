-- station_information is fetched once a day, so the same station appears once per day.
-- Keep every row here; dim_station picks the latest.
select
    cast(station_id as varchar) as station_id,
    snapshot_ts,
    name        as station_name,
    lat,
    lon,
    cast(capacity as integer) as capacity,
    address
from read_parquet(
    '{{ var("data_root") }}/station_information/*/*.parquet',
    hive_partitioning = true, union_by_name = true
)
