-- Current-snapshot customer dimension. SCD2 history lives in
-- snapshots/dim_customers_snapshot.sql, not here.
-- masked_customer_name/masked_customer_phone are intentionally excluded:
-- they're fixed mask literals ("MASKED_NAME"/"MASKED_PHONE") with no
-- analytical value.
-- total_orders/total_spent are aggregated here from stg_orders by the
-- natural customer_id, not the surrogate customer_key — fact_orders.sql
-- itself refs this model to resolve customer_key, so joining against
-- fact_orders here would be a circular dependency. Excludes 'placed'
-- orders (not yet past initial checkout), matching mart_sales_summary's
-- convention. Customers with no qualifying orders get 0, not NULL, so
-- they still count toward the average rather than being silently
-- dropped.
WITH order_totals AS (
    SELECT
        customer_id,
        COUNT(*)          AS total_orders,
        SUM(order_amount) AS total_spent
    FROM {{ ref('stg_orders') }}
    WHERE status != 'placed'
    GROUP BY customer_id
)

SELECT
    ROW_NUMBER() OVER (ORDER BY c.customer_id)   AS customer_key,
    c.customer_id,
    c.hashed_email,
    c.tier,
    c.registration_date,
    COALESCE(ot.total_orders, 0)                 AS total_orders,
    COALESCE(ot.total_spent, 0)                  AS total_spent
FROM {{ ref('stg_customers') }} c
LEFT JOIN order_totals ot ON c.customer_id = ot.customer_id
