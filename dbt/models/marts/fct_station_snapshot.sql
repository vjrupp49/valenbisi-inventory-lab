-- Grain: station x snapshot. Adds local time, staleness, stockout/blockout flags and the
-- change in bike count since the previous snapshot (inferred activity).
--
-- Definitions
--   is_stale     : station last reported more than `stale_after_hours` before the snapshot (or never).
--                  A stale count may be out of date rather than unchanged, so it is flagged, not trusted.
--   is_stockout  : installed, renting, and 0 bikes.      is_blockout : installed, returning, and 0 docks.
--   bikes_delta  : bikes - previous bikes, only when the previous snapshot is at most
--                  `max_delta_gap_minutes` earlier (otherwise null: we cannot tell what happened in a gap).
--   activity     : abs(bikes_delta). A LOWER BOUND on trips (an out and back between snapshots is invisible).
with base as (
    select
        s.*,
        d.capacity,
        -- Valencia local clock (handles daylight saving); used for hour-of-day and day-of-week
        timezone('Europe/Madrid', s.snapshot_ts) as local_ts
    from {{ ref('stg_station_status') }} s
    left join {{ ref('dim_station') }} d using (station_id)
),
lagged as (
    select
        *,
        lag(snapshot_ts) over w as prev_snapshot_ts,
        lag(bikes)       over w as prev_bikes
    from base
    window w as (partition by station_id order by snapshot_ts)
)
select
    station_id || '|' || cast(snapshot_ts as varchar) as snapshot_key,
    station_id,
    snapshot_ts,
    local_ts,
    cast(local_ts as date)          as local_date,
    hour(local_ts)                  as hour_of_day,
    isodow(local_ts)                as day_of_week,   -- 1 = Monday
    bikes,
    docks,
    capacity,
    bikes * 1.0 / nullif(capacity, 0) as availability,
    is_installed,
    is_renting,
    is_returning,
    last_reported,
    date_diff('second', last_reported, snapshot_ts) / 60.0 as minutes_since_report,
    coalesce(snapshot_ts - last_reported > to_hours({{ var('stale_after_hours') }}), true) as is_stale,
    (is_installed and is_renting and bikes = 0)    as is_stockout,
    (is_installed and is_returning and docks = 0)  as is_blockout,
    is_installed                                   as is_service_eligible,
    case when prev_snapshot_ts is not null
          and snapshot_ts - prev_snapshot_ts <= to_minutes({{ var('max_delta_gap_minutes') }})
         then bikes - prev_bikes end               as bikes_delta,
    case when prev_snapshot_ts is not null
          and snapshot_ts - prev_snapshot_ts <= to_minutes({{ var('max_delta_gap_minutes') }})
         then abs(bikes - prev_bikes) end          as activity
from lagged
