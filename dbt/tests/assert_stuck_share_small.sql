-- Warn if more than 3 % of installed, renting station-snapshots are flat for >= stuck_exclude_hours.
-- (On the frozen 2026-10 data, flat >= 12 h was 0.7 %.) A jump means many stations stopped updating.
{{ config(severity='warn') }}
select avg(is_stuck_excluded::int) as share_stuck_excluded
from {{ ref('fct_station_snapshot') }}
where is_installed and is_renting
having avg(is_stuck_excluded::int) > 0.03
