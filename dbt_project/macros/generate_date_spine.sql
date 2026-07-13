{#
    Generates a date spine (one row per calendar day) between start_date
    and end_date, inclusive. Used by models/marts/dimensions/dim_date.sql.
#}
{% macro generate_date_spine(start_date, end_date) %}
  SELECT
    CAST(TO_CHAR(d::DATE, 'YYYYMMDD') AS INT) AS date_key,
    d::DATE AS full_date,
    EXTRACT(YEAR FROM d)::INT AS year,
    EXTRACT(QUARTER FROM d)::INT AS quarter,
    EXTRACT(MONTH FROM d)::INT AS month,
    TRIM(TO_CHAR(d, 'Month')) AS month_name,
    EXTRACT(WEEK FROM d)::INT AS week_of_year,
    EXTRACT(DAY FROM d)::INT AS day_of_month,
    EXTRACT(ISODOW FROM d)::INT AS day_of_week,
    TRIM(TO_CHAR(d, 'Day')) AS day_name,
    EXTRACT(ISODOW FROM d) IN (6, 7) AS is_weekend
  FROM generate_series(
    '{{ start_date }}'::DATE,
    '{{ end_date }}'::DATE,
    '1 day'::INTERVAL
  ) AS t(d)
{% endmacro %}
