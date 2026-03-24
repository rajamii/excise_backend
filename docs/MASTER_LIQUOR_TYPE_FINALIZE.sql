-- Finalize master liquor type migration.
-- This removes the legacy text column `brand_warehouse.brand_type` so the table only stores liquor type as FK id.

BEGIN;

ALTER TABLE public.brand_warehouse
DROP COLUMN IF EXISTS brand_type;

COMMIT;

