-- product_key is nullable (customer_registered events have no
-- product_id). status always passes through as NULL currently — see
-- stg_events.sql's comment (staging.events has no such column yet).
SELECT
    ROW_NUMBER() OVER (ORDER BY e.event_timestamp, e.event_id)  AS event_key,
    e.event_id,
    e.event_type,
    e.event_timestamp,
    c.customer_key,
    p.product_key,
    d.date_key,
    e.order_id,
    e.order_amount,
    e.quantity,
    e.status
FROM {{ ref('stg_events') }} e
LEFT JOIN {{ ref('dim_customers') }} c ON e.customer_id = c.customer_id
LEFT JOIN {{ ref('dim_products') }} p ON e.product_id = p.product_id
LEFT JOIN {{ ref('dim_date') }} d ON CAST(TO_CHAR(e.event_timestamp, 'YYYYMMDD') AS INT) = d.date_key
