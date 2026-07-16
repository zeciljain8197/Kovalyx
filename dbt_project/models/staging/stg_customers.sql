-- shipping_address is intentionally excluded entirely: it's NULL
-- post-masking with no analytical value (same reasoning dim_customers
-- applies to the masked name/phone fields). total_orders/total_spent
-- aren't staged here — they're derived aggregates of stg_orders, not raw
-- attributes of the customer source table, so they're computed in
-- dim_customers.sql instead.
SELECT
    customer_id,
    email_hash                    AS hashed_email,
    customer_tier                 AS tier,
    CAST(registered_at AS DATE)   AS registration_date,
    -- masked fields kept for auditability, renamed for clarity
    full_name                     AS masked_customer_name,
    phone_masked                  AS masked_customer_phone
FROM {{ source('kovalyx_staging', 'customers') }}
WHERE customer_id IS NOT NULL
