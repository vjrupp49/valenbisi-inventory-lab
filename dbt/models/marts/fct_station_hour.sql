-- Grain: station x UTC hour. (UTC, not Madrid wall-clock, so the clock change on the last Sunday of October/March
-- cannot merge two real hours or create a phantom one. Madrid hour/date are attributes.)
-- Shares are over the snapshots that fell in the hour (n_snapshots varies because cron drifts/skips).
-- Stockout/blockout columns use only ELIGIBLE rows (see fct_station_snapshot); they are NULL when no row in the
-- hour is eligible.
select
    station_id || '|' || cast(date_trunc('hour', snapshot_ts) as varchar) as station_hour_key,
    station_id,
    date_trunc('hour', snapshot_ts)    as hour_utc,
    any_value(local_ts)                as local_ts_example,
    any_value(local_date)              as local_date,
    any_value(hour_of_day)             as hour_of_day,    -- Madrid hour
    any_value(day_of_week)             as day_of_week,    -- 1 = Monday
    bool_or(is_holiday)                as is_holiday,
    count(*)                           as n_snapshots,
    avg(bikes)                         as avg_bikes,
    min(bikes)                         as min_bikes,
    max(bikes)                         as max_bikes,
    avg(availability)                  as avg_availability,
    count(*) filter (where is_stockout_eligible) as n_stockout_eligible,
    avg(is_stockout::int) filter (where is_stockout_eligible) as stockout_share,
    bool_or(is_stockout)  filter (where is_stockout_eligible) as any_stockout,
    count(*) filter (where is_blockout_eligible) as n_blockout_eligible,
    avg(is_blockout::int) filter (where is_blockout_eligible) as blockout_share,
    bool_or(is_blockout)  filter (where is_blockout_eligible) as any_blockout,
    avg(is_stuck::int)                 as stuck_share,
    bool_or(is_stuck)                  as any_stuck,
    max(flat_hours)                    as max_flat_hours,
    coalesce(sum(activity), 0)         as activity_lower_bound,
    bool_and(is_service_eligible)      as is_service_eligible
from {{ ref('fct_station_snapshot') }}
group by station_id, date_trunc('hour', snapshot_ts)
