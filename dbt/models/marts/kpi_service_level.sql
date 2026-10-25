-- Stockout / blockout rate by station and Madrid hour-of-day, with data-coverage columns.
-- Three versions of each rate, from most to least inclusive:
--   *_rate_raw     : installed and renting (stockout) / returning (blockout) rows, nothing else removed
--   *_rate         : HEADLINE. raw minus rows where the count has been flat >= stuck_exclude_hours (12 h)
--   *_rate_strict  : raw minus rows flat >= stuck_flag_hours (6 h)
-- Where the versions differ a lot, stuck stations are driving the number.
-- Rates are lower bounds for stockouts: stockouts shorter than the 10-minute snapshot spacing can be missed.
-- is_provisional stays true until `min_days_final` distinct days are observed for that station-hour.
select
    station_id,
    hour_of_day,
    count(*)                                          as n_installed_rows,
    count(*) filter (where is_not_renting)            as n_not_renting_rows,
    count(*) filter (where is_stuck_excluded)         as n_stuck_excluded_rows,
    count(*) filter (where is_stockout_eligible)      as n_stockout_eligible,
    count(*) filter (where is_blockout_eligible)      as n_blockout_eligible,
    count(distinct local_date)                        as n_days_observed,
    min(local_date)                                   as first_date,
    max(local_date)                                   as last_date,
    avg(is_stockout::int) filter (where is_renting)                       as stockout_rate_raw,
    avg(is_stockout::int) filter (where is_stockout_eligible)             as stockout_rate,
    avg(is_stockout::int) filter (where is_renting and not is_stuck)      as stockout_rate_strict,
    avg(is_blockout::int) filter (where is_returning)                     as blockout_rate_raw,
    avg(is_blockout::int) filter (where is_blockout_eligible)             as blockout_rate,
    avg(is_blockout::int) filter (where is_returning and not is_stuck)    as blockout_rate_strict,
    count(distinct local_date) < {{ var('min_days_final') }} as is_provisional
from {{ ref('fct_station_snapshot') }}
where is_service_eligible
group by station_id, hour_of_day
