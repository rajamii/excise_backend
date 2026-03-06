-- Wallet balance schema/data alignment
-- 1) Add manufacturing_unit column.
-- 2) Keep old manufacturing value in manufacturing_unit.
-- 3) Store applicant/person in licensee_name.
-- 4) Force module_type=distillery when license_sub_category_id=2.

ALTER TABLE public.wallet_balances
ADD COLUMN IF NOT EXISTS manufacturing_unit character varying(150);

UPDATE public.wallet_balances
SET manufacturing_unit = COALESCE(NULLIF(manufacturing_unit, ''), NULLIF(licensee_name, ''))
WHERE COALESCE(NULLIF(manufacturing_unit, ''), '') = '';

UPDATE public.wallet_balances wb
SET manufacturing_unit = nla.establishment_name
FROM public.licenses l
JOIN public.new_license_application nla
  ON l.source_type = 'new_license_application'
 AND l.source_object_id = CAST(nla.application_id AS varchar)
WHERE l.license_id = wb.licensee_id
  AND COALESCE(NULLIF(nla.establishment_name, ''), '') <> '';

UPDATE public.wallet_balances wb
SET manufacturing_unit = la.establishment_name
FROM public.licenses l
JOIN public.license_application la
  ON l.source_type = 'license_application'
 AND l.source_object_id = CAST(la.application_id AS varchar)
WHERE l.license_id = wb.licensee_id
  AND COALESCE(NULLIF(la.establishment_name, ''), '') <> '';

UPDATE public.wallet_balances wb
SET licensee_name = nla.applicant_name
FROM public.licenses l
JOIN public.new_license_application nla
  ON l.source_type = 'new_license_application'
 AND l.source_object_id = CAST(nla.application_id AS varchar)
WHERE l.license_id = wb.licensee_id
  AND COALESCE(NULLIF(nla.applicant_name, ''), '') <> '';

UPDATE public.wallet_balances wb
SET licensee_name = la.member_name
FROM public.licenses l
JOIN public.license_application la
  ON l.source_type = 'license_application'
 AND l.source_object_id = CAST(la.application_id AS varchar)
WHERE l.license_id = wb.licensee_id
  AND COALESCE(NULLIF(la.member_name, ''), '') <> '';

UPDATE public.wallet_balances wb
SET licensee_name = TRIM(CONCAT_WS(' ', sb.first_name, sb.middle_name, sb.last_name))
FROM public.licenses l
JOIN public.salesman_barman_application sb
  ON l.source_type = 'salesman_barman'
 AND l.source_object_id = CAST(sb.application_id AS varchar)
WHERE l.license_id = wb.licensee_id
  AND COALESCE(NULLIF(TRIM(CONCAT_WS(' ', sb.first_name, sb.middle_name, sb.last_name)), ''), '') <> '';

UPDATE public.wallet_balances wb
SET module_type = 'distillery'
FROM public.licenses l
WHERE l.license_id = wb.licensee_id
  AND l.license_sub_category_id = 2
  AND COALESCE(wb.module_type, '') <> 'distillery';
