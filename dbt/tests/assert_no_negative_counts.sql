-- Hard check on real data: bike and dock counts can never be negative.
select station_id, snapshot_ts, bikes, docks
from {{ ref('stg_station_status') }}
where bikes < 0 or docks < 0
