-- days_of_stock_remaining always evaluates to NULL currently: units_sold
-- passes through as NULL from stg_inventory (staging.inventory has no
-- such column yet — see that model's comment), and the CASE guard below
-- is NULL-safe so this degrades gracefully rather than erroring.
SELECT
    ROW_NUMBER() OVER (ORDER BY i.product_id, d.date_key)  AS snapshot_key,
    p.product_key,
    d.date_key,
    i.stock_level,
    i.reorder_threshold,
    i.units_sold,
    i.units_received,
    (i.stock_level < i.reorder_threshold)                   AS is_below_reorder,
    CASE
        WHEN i.units_sold > 0 THEN i.stock_level::NUMERIC / i.units_sold
        ELSE NULL
    END                                                       AS days_of_stock_remaining
FROM {{ ref('stg_inventory') }} i
LEFT JOIN {{ ref('dim_products') }} p ON i.product_id = p.product_id
LEFT JOIN {{ ref('dim_date') }} d ON CAST(TO_CHAR(i.inventory_date, 'YYYYMMDD') AS INT) = d.date_key
