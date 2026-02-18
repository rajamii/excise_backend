from django.core.management.base import BaseCommand

from models.masters.supply_chain.profile.models import UserManufacturingUnit
from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouse


def _normalize(value: str) -> str:
    return ''.join(ch for ch in str(value or '').lower() if ch.isalnum())


class Command(BaseCommand):
    help = (
        "Backfill brand_warehouse.license_id from user_manufacturing_units using distillery/manufacturing unit name. "
        "Skips ambiguous name mappings."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print what would change without writing to DB.'
        )

    def handle(self, *args, **options):
        dry_run = bool(options.get('dry_run'))

        unit_map: dict[str, set[str]] = {}
        for row in UserManufacturingUnit.objects.exclude(manufacturing_unit_name__isnull=True).exclude(licensee_id__isnull=True):
            key = _normalize(row.manufacturing_unit_name)
            value = str(row.licensee_id or '').strip()
            if not key or not value:
                continue
            unit_map.setdefault(key, set()).add(value)

        pending = BrandWarehouse.objects.filter(license_id__isnull=True) | BrandWarehouse.objects.filter(license_id='')
        pending = pending.distinct().order_by('id')

        updated = 0
        skipped_no_match = 0
        skipped_ambiguous = 0

        for row in pending:
            key = _normalize(row.distillery_name)
            matches = sorted(unit_map.get(key, set()))
            if not matches:
                skipped_no_match += 1
                continue
            if len(matches) > 1:
                skipped_ambiguous += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"Ambiguous mapping for brand_warehouse.id={row.id} "
                        f"distillery='{row.distillery_name}' candidates={matches}"
                    )
                )
                continue

            target_license_id = matches[0]
            if dry_run:
                self.stdout.write(
                    f"[DRY RUN] brand_warehouse.id={row.id} -> license_id='{target_license_id}'"
                )
            else:
                row.license_id = target_license_id
                row.save(update_fields=['license_id', 'updated_at'])
            updated += 1

        summary = (
            f"Backfill completed. updated={updated}, "
            f"skipped_no_match={skipped_no_match}, skipped_ambiguous={skipped_ambiguous}, dry_run={dry_run}"
        )
        self.stdout.write(self.style.SUCCESS(summary))
