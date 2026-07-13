-- Fails if any product's inventory snapshot disagrees with its own
-- catalog entry on reorder_threshold (they should always match — see
-- scripts/seed_data.py's generate_inventory_snapshots(), which joins the
-- value directly from the products DataFrame).
SELECT i.product_id
FROM {{ ref('stg_inventory') }} i
JOIN {{ ref('stg_products') }} p USING (product_id)
WHERE i.reorder_threshold != p.reorder_threshold
