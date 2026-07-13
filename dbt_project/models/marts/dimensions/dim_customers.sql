-- Current-snapshot customer dimension. SCD2 history lives in
-- snapshots/dim_customers_snapshot.sql, not here.
-- masked_customer_name/masked_customer_phone are intentionally excluded:
-- they're fixed mask literals ("MASKED_NAME"/"MASKED_PHONE") with no
-- analytical value.
-- total_orders/total_spent currently pass through as NULL — see
-- stg_customers.sql's comment (staging.customers has no such columns yet).
SELECT
    ROW_NUMBER() OVER (ORDER BY customer_id)   AS customer_key,
    customer_id,
    hashed_email,
    tier,
    registration_date,
    total_orders,
    total_spent
FROM {{ ref('stg_customers') }}
