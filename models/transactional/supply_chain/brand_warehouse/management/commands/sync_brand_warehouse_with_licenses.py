from django.core.management.base import BaseCommand

from models.masters.license.models import License
from models.transactional.supply_chain.brand_warehouse.services import BrandWarehouseStockService


class Command(BaseCommand):
    help = (
        "Sync brand_warehouse rows with issued licenses using establishment_name and "
        "deduplicate rows by license/distillery/brand/size."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--license-id',
            type=str,
            help='Sync only one license_id (e.g. NA/1101/2025-26/0002).'
        )
        parser.add_argument(
            '--include-inactive',
            action='store_true',
            help='Include inactive licenses. By default only active licenses are synced.'
        )

    def handle(self, *args, **options):
        target_license_id = str(options.get('license_id') or '').strip()
        include_inactive = bool(options.get('include_inactive'))

        qs = License.objects.select_related('source_content_type').order_by('license_id')
        if not include_inactive:
            qs = qs.filter(is_active=True)
        if target_license_id:
            qs = qs.filter(license_id=target_license_id)

        processed = 0
        skipped = 0
        total_created = 0
        total_updated = 0
        total_deduplicated = 0

        for lic in qs:
            application = lic.source_application
            establishment_name = str(getattr(application, 'establishment_name', '') or '').strip()
            if not establishment_name:
                skipped += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"Skipping {lic.license_id}: establishment_name not found."
                    )
                )
                continue

            result = BrandWarehouseStockService.ensure_establishment_brands(
                license_id=lic.license_id,
                establishment_name=establishment_name
            )
            processed += 1
            total_created += int(result.get('created', 0) or 0)
            total_updated += int(result.get('updated', 0) or 0)
            total_deduplicated += int(result.get('deduplicated', 0) or 0)

            self.stdout.write(
                f"{lic.license_id} -> created={result.get('created', 0)} "
                f"updated={result.get('updated', 0)} deduplicated={result.get('deduplicated', 0)}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Sync completed. "
                f"processed={processed}, skipped={skipped}, created={total_created}, "
                f"updated={total_updated}, deduplicated={total_deduplicated}"
            )
        )
