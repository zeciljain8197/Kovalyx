-- Grain: one row per cohort_week x weeks_since_acquisition. Weekly
-- retention cohorts — cohort_week is the customer's registration week,
-- weeks_since_acquisition counts how many weeks after that cohort an
-- order happened.
WITH cohort_base AS (
    SELECT
        customer_id,
        DATE_TRUNC('week', registration_date) AS cohort_week
    FROM {{ ref('dim_customers') }}
    WHERE registration_date IS NOT NULL
),

order_activity AS (
    SELECT
        c.customer_id,
        DATE_TRUNC('week', d.full_date) AS order_week
    FROM {{ ref('fact_orders') }} fo
    JOIN {{ ref('dim_customers') }} c ON fo.customer_key = c.customer_key
    JOIN {{ ref('dim_date') }} d ON fo.date_key = d.date_key
),

cohort_size AS (
    SELECT
        cohort_week,
        COUNT(DISTINCT customer_id) AS customers_in_cohort
    FROM cohort_base
    GROUP BY cohort_week
),

retention AS (
    SELECT
        cb.cohort_week,
        EXTRACT(WEEK FROM (oa.order_week - cb.cohort_week))::INT AS weeks_since_acquisition,
        COUNT(DISTINCT oa.customer_id)                            AS active_customers
    FROM cohort_base cb
    JOIN order_activity oa ON cb.customer_id = oa.customer_id
    WHERE oa.order_week >= cb.cohort_week
    GROUP BY cb.cohort_week, EXTRACT(WEEK FROM (oa.order_week - cb.cohort_week))::INT
)

SELECT
    r.cohort_week,
    r.weeks_since_acquisition,
    cs.customers_in_cohort,
    r.active_customers,
    CASE
        WHEN cs.customers_in_cohort = 0 THEN NULL
        ELSE ROUND(r.active_customers::NUMERIC / cs.customers_in_cohort, 4)
    END AS retention_rate
FROM retention r
JOIN cohort_size cs ON r.cohort_week = cs.cohort_week
