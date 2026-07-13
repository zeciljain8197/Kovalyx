-- staging.orders has no card_type column at all (Pre-check 1) — exposed
-- as a typed NULL below; fact_orders.sql carries it through as NULL until
-- a schema migration adds a real column. card_last4 is kept for
-- completeness even though nothing downstream references it.
-- order_status is the real column name (status in the Silver contract).
-- shipping_address is intentionally excluded: NULL post-masking.
SELECT
    order_id,
    customer_id,
    product_id,
    quantity,
    unit_price,
    order_amount,
    CAST(order_date AS DATE)  AS order_date,
    order_status               AS status,
    NULL::TEXT                 AS card_last4,
    NULL::TEXT                 AS card_type
FROM {{ source('kovalyx_staging', 'orders') }}
WHERE order_id IS NOT NULL
