-- Grain: one row per product, current alert status as of its most recent
-- inventory snapshot.
WITH latest_snapshot AS (
    SELECT
        fis.*,
        ROW_NUMBER() OVER (PARTITION BY fis.product_key ORDER BY fis.date_key DESC) AS rn
    FROM {{ ref('fact_inventory_snapshots') }} fis
)

SELECT
    p.product_id,
    p.product_name,
    p.category,
    p.subcategory,
    p.supplier_id,
    ls.stock_level                       AS current_stock_level,
    ls.reorder_threshold,
    ls.days_of_stock_remaining,
    CASE
        WHEN ls.stock_level < ls.reorder_threshold THEN 'red'
        WHEN ls.stock_level < ls.reorder_threshold * 1.2 THEN 'yellow'
        ELSE 'green'
    END                                    AS alert_level,
    d.full_date                             AS snapshot_date
FROM latest_snapshot ls
JOIN {{ ref('dim_products') }} p ON ls.product_key = p.product_key
JOIN {{ ref('dim_date') }} d ON ls.date_key = d.date_key
WHERE ls.rn = 1
