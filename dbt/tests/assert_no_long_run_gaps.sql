-- Freshness-style check on run_meta: any gap between consecutive runs above `max_run_gap_hours`.
-- Severity is warn: GitHub cron skips happen and are expected to be measured, not to break the build.
{{ config(severity='warn') }}
select snapshot_ts, gap_minutes
from {{ ref('fct_run_health') }}
where gap_minutes > {{ var('max_run_gap_hours') }} * 60
