-- Warn if more than 0.1 % of installed rows have more bikes + docks + disabled than the station's capacity.
-- (On the frozen 2026-10 data this was 7 of 589,837 rows.)
{{ config(severity='warn') }}
select avg((bikes + docks + bikes_disabled + docks_disabled > capacity)::int) as share_above_capacity
from {{ ref('fct_station_snapshot') }}
where is_installed and capacity is not null
having avg((bikes + docks + bikes_disabled + docks_disabled > capacity)::int) > 0.001
