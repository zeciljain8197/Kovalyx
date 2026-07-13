-- Fails if any non-returned order has a zero or negative order_amount —
-- returned orders are allowed to net to <= 0 in downstream reporting, but
-- a live order never should be.
SELECT *
FROM {{ ref('fact_orders') }}
WHERE order_amount <= 0 AND status != 'returned'
