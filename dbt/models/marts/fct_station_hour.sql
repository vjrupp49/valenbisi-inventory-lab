-- Grain: station x local clock hour. Roll-up of fct_station_snapshot, used as forecasting features.
-- Shares are over the snapshots that fell in the hour (n_snapshots varies because cron drifts/skips).
select
    station_id || '|' || cast(date_trunc('hour', local_ts) as varchar) as station_hour_key,
    station_id,
    date_trunc('hour', local_ts)       as local_hour,
    any_value(local_date)              as local_date,
    any_value(hour_of_day)             as hour_of_day,
    any_value(day_of_week)             as day_of_week,
    count(*)                           as n_snapshots,
    count(*) filter (where not is_stale) as n_fresh_snapshots,
    avg(bikes)                         as avg_bikes,
    min(bikes)                         as min_bikes,
    max(bikes)                         as max_bikes,
    avg(availability)                  as avg_availability,
    avg(is_stockout::int)              as stockout_share,
    avg(is_blockout::int)              as blockout_share,
    bool_or(is_stockout)               as any_stockout,
    bool_or(is_blockout)               as any_blockout,
    avg(is_stale::int)                 as stale_share,
    bool_or(is_stale)                  as any_stale,
    coalesce(sum(activity), 0)         as activity_lower_bound,
    bool_and(is_service_eligible)      as is_service_eligible
from {{ ref('fct_station_snapshot') }}
group by station_id, date_trunc('hour', local_ts)
