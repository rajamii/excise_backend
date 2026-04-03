-- Add `is_sync` column to master/warehouse tables.
-- Default: 0 for all existing and new rows.

ALTER TABLE public.master_bottle_type
  ADD COLUMN IF NOT EXISTS is_sync integer NOT NULL DEFAULT 0;

ALTER TABLE public.master_liquor_type
  ADD COLUMN IF NOT EXISTS is_sync integer NOT NULL DEFAULT 0;

-- master_liquor_capacity endpoint maps to `master_liquor_category` (pack sizes)
ALTER TABLE public.master_liquor_category
  ADD COLUMN IF NOT EXISTS is_sync integer NOT NULL DEFAULT 0;

ALTER TABLE public.brand_warehouse
  ADD COLUMN IF NOT EXISTS is_sync integer NOT NULL DEFAULT 0;

