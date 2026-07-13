-- staging.products has no subcategory/supplier_id/current_stock columns
-- at all (Pre-check 1) — exposed as typed NULLs below; dim_products.sql
-- carries them through as NULL until a schema migration adds real
-- columns. reorder_point is the real column name (reorder_threshold in
-- the Silver contract) — aliased here for downstream consistency.
SELECT
    product_id,
    product_name,
    category,
    NULL::VARCHAR         AS subcategory,
    unit_price,
    cost_price,
    NULL::VARCHAR         AS supplier_id,
    reorder_point          AS reorder_threshold,
    NULL::INTEGER          AS current_stock
FROM {{ source('kovalyx_staging', 'products') }}
WHERE product_id IS NOT NULL
