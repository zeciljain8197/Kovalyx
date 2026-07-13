{# dbt_project.yml sets snapshot-paths: ["snapshots"], so this file lives
   at dbt_project/snapshots/ (dbt's convention), not models/snapshots/ —
   the session 1 scaffold placeholder at models/snapshots/ predates that
   config being pinned down and has been removed. #}
{% snapshot dim_customers_snapshot %}
{{
  config(
    target_schema='marts',
    unique_key='customer_id',
    strategy='check',
    check_cols=['tier', 'total_spent', 'total_orders'],
    invalidate_hard_deletes=True
  )
}}
-- Tracks tier changes and spending growth over time. masked_customer_name
-- and masked_customer_phone are excluded — fixed mask values with no
-- analytical meaning. dbt adds dbt_scd_id, dbt_updated_at, dbt_valid_from,
-- dbt_valid_to, dbt_is_current automatically.
SELECT
    customer_id,
    hashed_email,
    tier,
    registration_date,
    total_orders,
    total_spent
FROM {{ ref('stg_customers') }}
{% endsnapshot %}
