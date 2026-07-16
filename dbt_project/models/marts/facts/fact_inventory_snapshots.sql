-- units_sold/units_received still pass through as NULL from stg_inventory
-- (staging.inventory has no such columns — see that model's comment), so
-- days_of_stock_remaining can't be derived from them. Instead it's derived
-- from real sales velocity: each product's total units sold across the
-- full fact_orders date range, divided by the length of that window, gives
-- an average daily sell-through rate used to project the current stock
-- level forward. Products with no order history still degrade to NULL
-- (nothing to project from) rather than erroring.
WITH order_window AS (
    SELECT (MAX(d.full_date) - MIN(d.full_date) + 1) AS total_days
    FROM {{ ref('fact_orders') }} fo
    JOIN {{ ref('dim_date') }} d ON fo.date_key = d.date_key
),
product_velocity AS (
    SELECT
        fo.product_key,
        SUM(fo.quantity)::NUMERIC / NULLIF((SELECT total_days FROM order_window), 0) AS avg_daily_units_sold
    FROM {{ ref('fact_orders') }} fo
    WHERE fo.status != 'placed'
    GROUP BY fo.product_key
)
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
        WHEN pv.avg_daily_units_sold > 0 THEN ROUND(i.stock_level::NUMERIC / pv.avg_daily_units_sold, 1)
        ELSE NULL
    END                                                       AS days_of_stock_remaining
FROM {{ ref('stg_inventory') }} i
LEFT JOIN {{ ref('dim_products') }} p ON i.product_id = p.product_id
LEFT JOIN {{ ref('dim_date') }} d ON CAST(TO_CHAR(i.inventory_date, 'YYYYMMDD') AS INT) = d.date_key
LEFT JOIN product_velocity pv ON p.product_key = pv.product_key
