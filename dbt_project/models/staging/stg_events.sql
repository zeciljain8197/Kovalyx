-- staging.events (see sources.yml) predates the Session 2 bronze-contract
-- rewrite: it has no columns for product_name/category/card_last4/
-- card_type/stock_level/reorder_threshold/masked customer fields at all,
-- and no "status" column (fact_events needs status — exposed as a typed
-- NULL below until a schema migration adds it). None of the columns this
-- model drops are referenced by any downstream dimension/fact/mart model.
SELECT
    event_id,
    event_type,
    event_timestamp,
    order_id,
    customer_id,
    product_id,
    quantity,
    order_amount,
    NULL::TEXT AS status
FROM {{ source('kovalyx_staging', 'events') }}
WHERE event_id IS NOT NULL
