-- Fails if any order is dated after today — would indicate a clock skew
-- or data-generation bug upstream.
SELECT *
FROM {{ ref('stg_orders') }}
WHERE order_date > CURRENT_DATE
