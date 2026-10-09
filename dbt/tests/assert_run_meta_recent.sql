-- Opt-in recency check (enable with --vars '{check_recency: true}'): newest run must be younger than
-- max_run_gap_hours. Off by default so it does not trip on the committed SYNTHETIC sample or old local copies.
{{ config(severity='warn') }}
select max(snapshot_ts) as newest_run
from {{ ref('fct_run_health') }}
{% if var('check_recency') %}
having max(snapshot_ts) < now() - to_hours({{ var('max_run_gap_hours') }})
{% else %}
having false
{% endif %}
