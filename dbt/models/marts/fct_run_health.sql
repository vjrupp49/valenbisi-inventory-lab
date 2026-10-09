-- Grain: collector run. Measures gaps between runs instead of assuming a regular grid.
select
    snapshot_ts,
    ok,
    error,
    feed_age_s,
    n_installed,
    n_stale_1h,
    n_stale_1h * 1.0 / nullif(n_installed, 0) as stale_share,
    date_diff('second', lag(snapshot_ts) over (order by snapshot_ts), snapshot_ts) / 60.0 as gap_minutes
from {{ ref('stg_run_meta') }}
