-- Add stable stock-scoping key to brand_warehouse.
ALTER TABLE public.brand_warehouse
ADD COLUMN IF NOT EXISTS license_id VARCHAR(100);

CREATE INDEX IF NOT EXISTS idx_brand_warehouse_license_id
ON public.brand_warehouse (license_id);

-- Optional one-time backfill by exact unit-name match.
-- Review result after running; ambiguous unit names should be handled manually.
UPDATE public.brand_warehouse bw
SET license_id = u.licensee_id
FROM (
  SELECT DISTINCT ON (LOWER(TRIM(manufacturing_unit_name)))
         LOWER(TRIM(manufacturing_unit_name)) AS unit_key,
         licensee_id
  FROM public.user_manufacturing_units
  WHERE COALESCE(TRIM(manufacturing_unit_name), '') <> ''
    AND COALESCE(TRIM(licensee_id), '') <> ''
  ORDER BY LOWER(TRIM(manufacturing_unit_name)), updated_at DESC, id DESC
) u
WHERE (bw.license_id IS NULL OR TRIM(bw.license_id) = '')
  AND LOWER(TRIM(bw.distillery_name)) = u.unit_key;
