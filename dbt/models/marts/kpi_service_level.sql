-- Stockout / blockout rate by station and local hour-of-day, with data-coverage columns.
-- Rates are over installed stations only. Two versions of each rate:
--   *_rate_all   : every snapshot (stale counts included; may be out of date)
--   *_rate_fresh : only snapshots where the station reported within the staleness window
-- Compare them; where they differ a lot, staleness is driving the number.
-- is_provisional stays true until `min_days_final` distinct days are observed for that station-hour.
select
    station_id,
    hour_of_day,
    count(*)                                   as n_snapshots,
    count(*) filter (where not is_stale)       as n_fresh_snapshots,
    count(distinct local_date)                 as n_days_observed,
    min(local_date)                            as first_date,
    max(local_date)                            as last_date,
    avg(is_stale::int)                         as stale_share,
    avg(is_stockout::int)                      as stockout_rate_all,
    avg(is_stockout::int) filter (where not is_stale) as stockout_rate_fresh,
    avg(is_blockout::int)                      as blockout_rate_all,
    avg(is_blockout::int) filter (where not is_stale) as blockout_rate_fresh,
    count(distinct local_date) < {{ var('min_days_final') }} as is_provisional
from {{ ref('fct_station_snapshot') }}
where is_service_eligible
group by station_id, hour_of_day
