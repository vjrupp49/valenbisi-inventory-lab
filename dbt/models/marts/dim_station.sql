-- One row per station. Base = every station ever seen in station_status (so a station missing
-- from station_information is still visible); attributes come from the latest information row.
with seen as (
    select
        station_id,
        min(snapshot_ts) as first_seen_ts,
        max(snapshot_ts) as last_seen_ts,
        -- "latest" installed flag = value at the most recent snapshot
        arg_max(is_installed, snapshot_ts) as is_installed_latest
    from {{ ref('stg_station_status') }}
    group by station_id
),
latest_info as (
    select *
    from {{ ref('stg_station_information') }}
    qualify row_number() over (partition by station_id order by snapshot_ts desc) = 1
)
select
    s.station_id,
    i.station_name,
    i.lat,
    i.lon,
    i.capacity,
    i.address,
    s.first_seen_ts,
    s.last_seen_ts,
    s.is_installed_latest
from seen s
left join latest_info i using (station_id)
