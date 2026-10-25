-- Warn if the number of stations per snapshot swings by more than 5 across the data
-- (the frozen 2026-10 data went from 276 to 277 once, on Oct 15).
{{ config(severity='warn') }}
select min(n) as min_stations, max(n) as max_stations
from (select snapshot_ts, count(*) as n from {{ ref('stg_station_status') }} group by 1)
having max(n) - min(n) > 5
