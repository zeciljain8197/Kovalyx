-- staging.customers has no total_orders/total_spent columns at all (Pre-
-- check 1) — exposed as typed NULLs below; dim_customers.sql and the SCD2
-- snapshot both carry them through as NULL until a schema migration adds
-- real columns. shipping_address is intentionally excluded entirely: it's
-- NULL post-masking with no analytical value (same reasoning dim_customers
-- applies to the masked name/phone fields).
SELECT
    customer_id,
    email_hash                    AS hashed_email,
    customer_tier                 AS tier,
    CAST(registered_at AS DATE)   AS registration_date,
    NULL::INTEGER                 AS total_orders,
    NULL::NUMERIC(12, 2)          AS total_spent,
    -- masked fields kept for auditability, renamed for clarity
    full_name                     AS masked_customer_name,
    phone_masked                  AS masked_customer_phone
FROM {{ source('kovalyx_staging', 'customers') }}
WHERE customer_id IS NOT NULL
