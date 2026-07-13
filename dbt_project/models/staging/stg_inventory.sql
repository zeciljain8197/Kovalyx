-- staging.inventory has no units_sold/units_received columns at all
-- (Pre-check 1) — exposed as typed NULLs below; fact_inventory_snapshots
-- .days_of_stock_remaining will always evaluate to NULL until a schema
-- migration adds real columns (its CASE WHEN units_sold > 0 guard is
-- NULL-safe, so this degrades gracefully rather than erroring).
SELECT
    product_id,
    snapshot_date          AS inventory_date,
    quantity_on_hand        AS stock_level,
    reorder_point            AS reorder_threshold,
    NULL::INTEGER             AS units_sold,
    NULL::INTEGER             AS units_received
FROM {{ source('kovalyx_staging', 'inventory') }}
WHERE product_id IS NOT NULL
  AND snapshot_date IS NOT NULL
