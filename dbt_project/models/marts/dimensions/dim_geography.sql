-- Address data is masked at Silver layer for privacy. Geography dimension
-- is a placeholder to maintain star schema integrity. Future enhancement:
-- derive region from product category distribution or user-provided
-- region tags.
SELECT *
FROM (
    VALUES
        (1, 'Unknown — address masked for privacy')
) AS geography (geography_key, geography_name)
