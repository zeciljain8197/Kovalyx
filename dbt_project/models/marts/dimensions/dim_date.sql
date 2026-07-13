-- Date spine from kovalyx_start_date (2024-01-01, see dbt_project.yml
-- vars) through 2026-12-31. No FK constraints; date_key is the primary
-- key every fact table joins against.
{{ generate_date_spine(var('kovalyx_start_date'), '2026-12-31') }}
