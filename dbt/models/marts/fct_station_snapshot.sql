-- Grain: station x snapshot. Adds Madrid local time, data-quality flags, stockout/blockout flags and the change
-- in bike count since the previous snapshot (inferred activity).
--
-- Definitions (decided 2026-10-25, docs/analysis_charter.md)
--   flat_hours          : hours since this station's bike count last changed (a lower bound at the start of the data).
--   is_stuck            : flat_hours >= stuck_flag_hours (6).  The count may be out of date or the station dead.
--   is_stuck_excluded   : flat_hours >= stuck_exclude_hours (12). Left out of headline stockout/blockout rates.
--   last_reported_age_hours : INFORMATION ONLY. last_reported barely moves when counts do, so it is not a quality gate.
--   is_stockout / is_blockout : RAW. installed + renting + 0 bikes  /  installed + returning + 0 free docks.
--   is_stockout_eligible / is_blockout_eligible : installed + renting (or returning) minus stuck-excluded rows.
--                          Use these as the population for headline rates.
--   is_not_renting      : installed but bikes cannot be taken (an out-of-service spell).
--   bikes_delta         : bikes - previous bikes, only when the previous snapshot is at most `max_delta_gap_minutes`
--                          earlier (otherwise null: we cannot tell what happened in a gap).
--   activity            : abs(bikes_delta). A LOWER BOUND on trips (an out and back between snapshots is invisible).
--   capacity            : the capacity valid at the snapshot (as-of join on the daily station_information rows).
--   availability        : bikes / capacity, an APPROXIMATE fill ratio (13 % of rows do not add up to capacity).
with base as (
    select
        s.*,
        coalesce(i.capacity, d.capacity) as capacity,
        -- Madrid wall clock (handles daylight saving); used for hour-of-day and day-of-week
        timezone('Europe/Madrid', s.snapshot_ts) as local_ts
    from {{ ref('stg_station_status') }} s
    asof left join {{ ref('stg_station_information') }} i
        on s.station_id = i.station_id and s.snapshot_ts >= i.snapshot_ts
    left join {{ ref('dim_station') }} d on d.station_id = s.station_id
),
lagged as (
    select
        *,
        lag(snapshot_ts) over w as prev_snapshot_ts,
        lag(bikes)       over w as prev_bikes,
        min(snapshot_ts) over (partition by station_id) as first_ts
    from base
    window w as (partition by station_id order by snapshot_ts)
),
changes as (
    select
        *,
        -- time of the most recent change in the bike count (null until the first change)
        max(case when prev_bikes is not null and bikes <> prev_bikes then snapshot_ts end)
            over (partition by station_id order by snapshot_ts
                  rows between unbounded preceding and current row) as last_change_ts
    from lagged
),
flagged as (
    select
        *,
        date_diff('second', coalesce(last_change_ts, first_ts), snapshot_ts) / 3600.0 as flat_hours
    from changes
)
select
    f.station_id || '|' || cast(f.snapshot_ts as varchar) as snapshot_key,
    f.station_id,
    f.snapshot_ts,
    f.local_ts,
    cast(f.local_ts as date)          as local_date,
    hour(f.local_ts)                  as hour_of_day,
    isodow(f.local_ts)                as day_of_week,   -- 1 = Monday
    (h.holiday_date is not null)      as is_holiday,
    f.bikes,
    f.docks,
    f.bikes_disabled,
    f.docks_disabled,
    f.capacity,
    f.bikes * 1.0 / nullif(f.capacity, 0) as availability,
    f.is_installed,
    f.is_renting,
    f.is_returning,
    f.last_reported,
    date_diff('second', f.last_reported, f.snapshot_ts) / 3600.0 as last_reported_age_hours,
    f.flat_hours,
    (f.flat_hours >= {{ var('stuck_flag_hours') }})    as is_stuck,
    (f.flat_hours >= {{ var('stuck_exclude_hours') }}) as is_stuck_excluded,
    (f.is_installed and not f.is_renting)              as is_not_renting,
    (f.is_installed and f.is_renting and f.bikes = 0)   as is_stockout,
    (f.is_installed and f.is_returning and f.docks = 0) as is_blockout,
    (f.is_installed and f.is_renting
        and f.flat_hours < {{ var('stuck_exclude_hours') }})   as is_stockout_eligible,
    (f.is_installed and f.is_returning
        and f.flat_hours < {{ var('stuck_exclude_hours') }})   as is_blockout_eligible,
    f.is_installed                                     as is_service_eligible,
    case when f.prev_snapshot_ts is not null
          and f.snapshot_ts - f.prev_snapshot_ts <= to_minutes({{ var('max_delta_gap_minutes') }})
         then f.bikes - f.prev_bikes end               as bikes_delta,
    case when f.prev_snapshot_ts is not null
          and f.snapshot_ts - f.prev_snapshot_ts <= to_minutes({{ var('max_delta_gap_minutes') }})
         then abs(f.bikes - f.prev_bikes) end          as activity
from flagged f
left join {{ ref('holidays') }} h on h.holiday_date = cast(f.local_ts as date)
