-- Add stable license scoping key to brand_warehouse_arrival.
ALTER TABLE public.brand_warehouse_arrival
ADD COLUMN IF NOT EXISTS license_id VARCHAR(100);

CREATE INDEX IF NOT EXISTS idx_brand_warehouse_arrival_license_id
ON public.brand_warehouse_arrival (license_id);

-- Backfill from related brand_warehouse rows.
UPDATE public.brand_warehouse_arrival bwa
SET license_id = bw.license_id
FROM public.brand_warehouse bw
WHERE bwa.brand_warehouse_id = bw.id
  AND (bwa.license_id IS NULL OR TRIM(bwa.license_id) = '')
  AND COALESCE(TRIM(bw.license_id), '') <> '';

