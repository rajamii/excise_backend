from django.core.management.base import BaseCommand
from django.db import transaction
from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouse


class Command(BaseCommand):
    help = 'Verify brand_warehouse inventory dataset without liquor_data_details dependency'

    def handle(self, *args, **options):
        self.stdout.write('Verifying Brand Warehouse records...')
        self.stdout.write('=' * 60)

        with transaction.atomic():
            total_warehouse_entries = BrandWarehouse.objects.count()
            self.stdout.write(f'Total BrandWarehouse entries: {total_warehouse_entries}')

            unique_distilleries = (
                BrandWarehouse.objects.values_list('distillery_name', flat=True)
                .distinct()
                .count()
            )
            self.stdout.write(f'Unique distilleries: {unique_distilleries}')

            pack_sizes = list(
                BrandWarehouse.objects.values_list('capacity_size__size_ml', flat=True)
                .distinct()
                .order_by('capacity_size__size_ml')
            )
            self.stdout.write(f'Available pack sizes: {pack_sizes}')

            sikkim_brands = BrandWarehouse.objects.filter(
                distillery_name__icontains='Sikkim Distilleries Ltd'
            ).count()
            self.stdout.write(f'Sikkim Distilleries Ltd rows: {sikkim_brands}')

            missing_rates = BrandWarehouse.objects.filter(
                ex_factory_price_rs_per_case__isnull=True
            ).count()
            self.stdout.write(f'Rows missing ex-factory rate: {missing_rates}')

        self.stdout.write('\nBrandWarehouse verification completed.')
        self.stdout.write('No liquor_data_details reads in this command.')
