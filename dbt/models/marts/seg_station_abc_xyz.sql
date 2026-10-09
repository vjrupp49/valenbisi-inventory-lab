-- ABC / XYZ segmentation of stations, using inferred activity as the "turnover" measure.
--   ABC (value)       : rank stations by mean daily activity; A = stations making up the first 80 % of
--                       total activity, B = next 15 %, C = the rest (cutoffs in dbt_project.yml).
--   XYZ (variability) : coefficient of variation (sd / mean) of DAILY activity.
--                       X <= 0.5 (stable), Y <= 1.0, Z > 1.0 (erratic). Mean 0 => 'n/a'.
-- Only days with >= `min_snapshots_per_day` snapshots count, so partial days do not distort the CV.
-- Everything is provisional until `min_days_final` usable days exist for the station.
-- Activity is a lower bound on trips (see fct_station_snapshot).
with daily as (
    select
        station_id,
        local_date,
        sum(activity) as daily_activity
    from {{ ref('fct_station_snapshot') }}
    where is_service_eligible
    group by station_id, local_date
    having count(*) >= {{ var('min_snapshots_per_day') }}
),
per_station as (
    select
        station_id,
        count(*)                              as n_days_used,
        avg(daily_activity)                   as mean_daily_activity,
        stddev_samp(daily_activity)           as sd_daily_activity
    from daily
    group by station_id
),
ranked as (
    select
        *,
        -- activity of all busier stations (running total excluding this row)
        sum(mean_daily_activity) over (order by mean_daily_activity desc, station_id
                                       rows between unbounded preceding and 1 preceding) as cum_before,
        sum(mean_daily_activity) over () as total_activity
    from per_station
)
select
    d.station_id,
    coalesce(r.n_days_used, 0)            as n_days_used,
    r.mean_daily_activity,
    r.sd_daily_activity,
    r.sd_daily_activity / nullif(r.mean_daily_activity, 0) as cv_daily_activity,
    case
        when r.station_id is null then 'n/a'
        when r.total_activity = 0 then 'C'
        when coalesce(r.cum_before, 0) / r.total_activity < {{ var('abc_a_cutoff') }} then 'A'
        when coalesce(r.cum_before, 0) / r.total_activity < {{ var('abc_b_cutoff') }} then 'B'
        else 'C'
    end                                   as abc_class,
    case
        when r.station_id is null or r.mean_daily_activity = 0 or r.sd_daily_activity is null then 'n/a'
        when r.sd_daily_activity / r.mean_daily_activity <= {{ var('xyz_x_max_cv') }} then 'X'
        when r.sd_daily_activity / r.mean_daily_activity <= {{ var('xyz_y_max_cv') }} then 'Y'
        else 'Z'
    end                                   as xyz_class,
    coalesce(r.n_days_used, 0) < {{ var('min_days_final') }} as is_provisional
from {{ ref('dim_station') }} d
left join ranked r using (station_id)
where d.is_installed_latest
