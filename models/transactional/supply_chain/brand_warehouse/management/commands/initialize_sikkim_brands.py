from django.core.management.base import BaseCommand
from models.transactional.supply_chain.brand_warehouse.services import BrandWarehouseStockService


class Command(BaseCommand):
    help = 'Initialize ALL Sikkim brands in Brand Warehouse (ensures no brands go missing)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without actually creating entries',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        self.stdout.write(
            self.style.SUCCESS('🏭 Initializing ALL Sikkim brands in Brand Warehouse...')
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('🔍 DRY RUN MODE - No changes will be made')
            )
        
        try:
            if not dry_run:
                # Get all Sikkim brands and ensure they have warehouse entries
                all_brands = BrandWarehouseStockService.get_all_sikkim_brands_with_stock()
                
                self.stdout.write(f"✅ Processed {all_brands.count()} Sikkim brands")
                
                # Show summary
                total_stock = sum(brand.current_stock for brand in all_brands)
                new_brands = sum(1 for brand in all_brands if BrandWarehouseStockService.check_if_brand_is_new(brand))
                out_of_stock = sum(1 for brand in all_brands if brand.status == 'OUT_OF_STOCK')
                in_stock = sum(1 for brand in all_brands if brand.status == 'IN_STOCK')
                
                self.stdout.write("\n" + "="*50)
                self.stdout.write(f"📊 Summary:")
                self.stdout.write(f"   Total Brands: {all_brands.count()}")
                self.stdout.write(f"   Total Stock: {total_stock} units")
                self.stdout.write(f"   NEW Brands (recent updates): {new_brands}")
                self.stdout.write(f"   In Stock: {in_stock}")
                self.stdout.write(f"   Out of Stock: {out_of_stock}")
                
                # Show some examples
                self.stdout.write(f"\n📋 Sample brands:")
                for brand in all_brands[:5]:
                    new_tag = "🆕 NEW" if BrandWarehouseStockService.check_if_brand_is_new(brand) else ""
                    self.stdout.write(f"   • {brand.brand_details} ({brand.capacity_size}ml) - Stock: {brand.current_stock} {new_tag}")
                
                if all_brands.count() > 5:
                    self.stdout.write(f"   ... and {all_brands.count() - 5} more brands")
                
            else:
                # Dry run - just show what would happen
                all_brands = BrandWarehouseStockService.get_all_sikkim_brands_with_stock()
                self.stdout.write(f"📊 Would process {all_brands.count()} Sikkim brand_warehouse rows")
                
                # Show examples
                for brand in all_brands[:5]:
                    self.stdout.write(f"   • {brand.brand_details} ({brand.capacity_size}ml) - {brand.distillery_name}")
                
                if all_brands.count() > 5:
                    self.stdout.write(f"   ... and {all_brands.count() - 5} more")
            
            self.stdout.write(
                self.style.SUCCESS('\n✅ All Sikkim brands are now available in Brand Warehouse!')
            )
            self.stdout.write(
                self.style.SUCCESS('🎯 No brands will go missing - all brands are always shown!')
            )
            
            if dry_run:
                self.stdout.write(
                    self.style.WARNING('\n🔍 This was a dry run. Run without --dry-run to make changes.')
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error: {str(e)}')
            )
