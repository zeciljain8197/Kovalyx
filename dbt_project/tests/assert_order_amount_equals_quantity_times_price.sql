-- Fails if any row's order_amount drifts from quantity * unit_price by
-- more than a cent (rounding tolerance).
SELECT *
FROM {{ ref('stg_orders') }}
WHERE ABS(order_amount - ROUND(quantity * unit_price, 2)) > 0.01
