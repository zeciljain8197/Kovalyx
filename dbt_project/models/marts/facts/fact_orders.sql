-- geography_key is hardcoded to 1 (dim_geography's single placeholder
-- row) rather than joined — there's no address data left post-masking to
-- join on. customer_key/product_key/date_key are left as whatever the
-- LEFT JOIN produces (NULL only on a genuine orphan) instead of being
-- COALESCEd to a fabricated "unknown" surrogate: dim_customers/
-- dim_products have no unknown-member row, so coalescing to a made-up key
-- would violate the relationships tests in models/schema.yml rather than
-- satisfy them. In this dataset every order's customer_id/product_id
-- originates from the same pools that seed the dimensions, so orphans
-- shouldn't occur in practice.
SELECT
    ROW_NUMBER() OVER (ORDER BY o.order_id)  AS order_key,
    o.order_id,
    c.customer_key,
    p.product_key,
    d.date_key,
    1                                         AS geography_key,
    o.quantity,
    o.unit_price,
    o.order_amount,
    o.status,
    o.card_type,
    (o.status = 'returned')                   AS is_returned
FROM {{ ref('stg_orders') }} o
LEFT JOIN {{ ref('dim_customers') }} c ON o.customer_id = c.customer_id
LEFT JOIN {{ ref('dim_products') }} p ON o.product_id = p.product_id
LEFT JOIN {{ ref('dim_date') }} d ON CAST(TO_CHAR(o.order_date, 'YYYYMMDD') AS INT) = d.date_key
