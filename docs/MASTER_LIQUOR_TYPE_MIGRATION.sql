-- Create master liquor type table and link it to brand_warehouse via FK id.
-- Target DB: PostgreSQL
--
-- Notes:
-- - This script assumes the legacy column `brand_warehouse.brand_type` exists and contains liquor type names.
-- - After backfilling `brand_warehouse.liquor_type`, you may optionally drop the legacy column.
-- - The backend code reads `brand_warehouse.liquor_type` (FK) and exposes `brand_type` as a computed display field.

BEGIN;

-- 1) Master table
CREATE TABLE IF NOT EXISTS public.master_liquor_type (
    id BIGSERIAL PRIMARY KEY,
    liquor_type VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Ensure a fallback type always exists.
INSERT INTO public.master_liquor_type (liquor_type)
VALUES ('Other')
ON CONFLICT (liquor_type) DO NOTHING;

-- 2) Seed master list from existing brand_warehouse rows
INSERT INTO public.master_liquor_type (liquor_type)
SELECT DISTINCT NULLIF(TRIM(bw.brand_type), '') AS liquor_type
FROM public.brand_warehouse bw
WHERE bw.brand_type IS NOT NULL
  AND TRIM(bw.brand_type) <> ''
ON CONFLICT (liquor_type) DO NOTHING;

-- 3) Add FK column to brand_warehouse
ALTER TABLE public.brand_warehouse
ADD COLUMN IF NOT EXISTS liquor_type BIGINT;

-- 4) Backfill FK values
UPDATE public.brand_warehouse bw
SET liquor_type = mlt.id
FROM public.master_liquor_type mlt
WHERE bw.liquor_type IS NULL
  AND COALESCE(NULLIF(TRIM(bw.brand_type), ''), 'Other') = mlt.liquor_type;

-- Any remaining NULLs get mapped to 'Other'
UPDATE public.brand_warehouse bw
SET liquor_type = (SELECT id FROM public.master_liquor_type WHERE liquor_type = 'Other')
WHERE bw.liquor_type IS NULL;

-- 5) Add FK + index (id stored in brand_warehouse.liquor_type)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'fk_brand_warehouse_liquor_type'
  ) THEN
    ALTER TABLE public.brand_warehouse
      ADD CONSTRAINT fk_brand_warehouse_liquor_type
      FOREIGN KEY (liquor_type)
      REFERENCES public.master_liquor_type(id);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_brand_warehouse_liquor_type
ON public.brand_warehouse (liquor_type);

-- 6) Optional cleanup (only after verifying all modules)
-- ALTER TABLE public.brand_warehouse DROP COLUMN IF EXISTS brand_type;

COMMIT;

