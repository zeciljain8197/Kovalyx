-- subcategory/supplier_id/current_stock currently pass through as NULL —
-- see stg_products.sql's comment (staging.products has no such columns
-- yet). margin_pct is guarded against unit_price = 0 to avoid a
-- division-by-zero error.
SELECT
    ROW_NUMBER() OVER (ORDER BY product_id)                            AS product_key,
    product_id,
    product_name,
    category,
    subcategory,
    unit_price,
    cost_price,
    CASE
        WHEN unit_price IS NULL OR unit_price = 0 THEN NULL
        ELSE ROUND((unit_price - cost_price) / unit_price * 100, 2)
    END                                                                 AS margin_pct,
    supplier_id,
    reorder_threshold,
    current_stock
FROM {{ ref('stg_products') }}
