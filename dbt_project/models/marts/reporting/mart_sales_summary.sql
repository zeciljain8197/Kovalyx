-- Grain: one row per day per category. Excludes orders still at 'placed'
-- (not yet progressed past initial checkout) per the spec's WHERE clause.
SELECT
    d.full_date                                                          AS period_date,
    d.year,
    d.month,
    d.week_of_year,
    p.category,
    p.subcategory,
    COUNT(*)                                                             AS total_orders,
    SUM(fo.order_amount)                                                 AS total_gmv,
    CASE WHEN COUNT(*) = 0 THEN NULL ELSE ROUND(SUM(fo.order_amount) / COUNT(*), 2) END AS avg_order_value,
    COUNT(DISTINCT fo.customer_key)                                      AS unique_customers,
    SUM(fo.quantity)                                                     AS total_items_sold,
    COUNT(*) FILTER (WHERE fo.status = 'returned')                       AS returned_orders,
    CASE
        WHEN COUNT(*) = 0 THEN NULL
        ELSE ROUND(COUNT(*) FILTER (WHERE fo.status = 'returned')::NUMERIC / COUNT(*), 4)
    END                                                                   AS return_rate
FROM {{ ref('fact_orders') }} fo
LEFT JOIN {{ ref('dim_products') }} p ON fo.product_key = p.product_key
LEFT JOIN {{ ref('dim_date') }} d ON fo.date_key = d.date_key
WHERE fo.status != 'placed'
GROUP BY d.full_date, d.year, d.month, d.week_of_year, p.category, p.subcategory
