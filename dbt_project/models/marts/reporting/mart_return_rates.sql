-- Grain: one row per month per product.
WITH monthly AS (
    SELECT
        d.year,
        d.month,
        DATE_TRUNC('month', d.full_date)::DATE                    AS period_date,
        p.product_id,
        p.product_name,
        p.category,
        COUNT(*)                                                    AS total_orders,
        COUNT(*) FILTER (WHERE fo.status = 'returned')               AS returned_orders,
        CASE
            WHEN COUNT(*) = 0 THEN NULL
            ELSE ROUND(COUNT(*) FILTER (WHERE fo.status = 'returned')::NUMERIC / COUNT(*), 4)
        END                                                           AS return_rate
    FROM {{ ref('fact_orders') }} fo
    JOIN {{ ref('dim_products') }} p ON fo.product_key = p.product_key
    JOIN {{ ref('dim_date') }} d ON fo.date_key = d.date_key
    GROUP BY d.year, d.month, DATE_TRUNC('month', d.full_date)::DATE, p.product_id, p.product_name, p.category
)

SELECT
    year,
    month,
    period_date,
    product_id,
    product_name,
    category,
    total_orders,
    returned_orders,
    return_rate,
    LAG(return_rate, 1) OVER (PARTITION BY product_id ORDER BY year, month) AS prev_month_return_rate,
    return_rate - LAG(return_rate, 1) OVER (PARTITION BY product_id ORDER BY year, month) AS return_rate_change
FROM monthly
