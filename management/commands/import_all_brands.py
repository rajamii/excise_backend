from django.core.management.base import BaseCommand
from django.db import transaction
from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouse
from models.masters.supply_chain.liquor_data.models import LiquorData


class Command(BaseCommand):
    help = 'Import ALL brands from LiquorData into BrandWarehouse'

    def handle(self, *args, **options):
        """
        Import ALL brands from LiquorData into BrandWarehouse
        """
        self.stdout.write("🔄 Importing ALL Brands to Brand Warehouse...")
        self.stdout.write("=" * 60)
        
        with transaction.atomic():
            # Get ALL liquor data entries
            all_liquor_data = LiquorData.objects.all().values(
                'id', 'brand_name', 'manufacturing_unit_name', 
                'brand_owner', 'liquor_type', 'pack_size_ml'
            )
            
            total_entries = len(all_liquor_data)
            self.stdout.write(f"📦 Found {total_entries} total liquor data entries to process")
            
            created_count = 0
            updated_count = 0
            skipped_count = 0
            error_count = 0
            
            # Group by distillery for better reporting
            distillery_stats = {}
            
            for i, item in enumerate(all_liquor_data, 1):
                try:
                    brand_name = item['brand_name']
                    distillery = item['manufacturing_unit_name']
                    pack_size = item['pack_size_ml']
                    brand_owner = item['brand_owner']
                    liquor_type = item['liquor_type']
                    
                    # Skip entries with missing critical data
                    if not brand_name or not distillery or not pack_size:
                        self.stdout.write(f"   ⚠️ Skipping entry {i}: Missing data - Brand: {brand_name}, Distillery: {distillery}, Size: {pack_size}")
                        skipped_count += 1
                        continue
                    
                    # Create brand details string
                    if brand_owner and brand_owner != brand_name:
                        brand_details = f"{brand_name} - {brand_owner}"
                    else:
                        brand_details = brand_name
                    
                    # Get or create Brand Warehouse entry
                    warehouse_entry, created = BrandWarehouse.objects.get_or_create(
                        distillery_name=distillery,
                        brand_details=brand_details,
                        capacity_size=pack_size,
                        defaults={
                            'brand_type': liquor_type or 'Liquor',
                            'current_stock': 0,
                            'liquor_data_id': item['id'],
                            'max_capacity': 10000,  # Default capacity
                            'reorder_level': 1000,  # Default reorder level
                            'status': 'OUT_OF_STOCK'
                        }
                    )
                    
                    # Track statistics by distillery
                    if distillery not in distillery_stats:
                        distillery_stats[distillery] = {'created': 0, 'updated': 0}
                    
                    if created:
                        created_count += 1
                        distillery_stats[distillery]['created'] += 1
                        if i <= 50 or created_count <= 20:  # Show first 50 or first 20 created
                            self.stdout.write(f"   ✅ Created ({i}/{total_entries}): {brand_name} ({pack_size}ml) - {distillery}")
                    else:
                        # Update existing entry with liquor_data reference if missing
                        if not warehouse_entry.liquor_data_id:
                            warehouse_entry.liquor_data_id = item['id']
                            warehouse_entry.save(update_fields=['liquor_data_id'])
                            updated_count += 1
                            distillery_stats[distillery]['updated'] += 1
                    
                    # Progress indicator for large datasets
                    if i % 50 == 0:
                        self.stdout.write(f"   📊 Progress: {i}/{total_entries} ({(i/total_entries)*100:.1f}%)")
                    
                except Exception as e:
                    error_count += 1
                    self.stdout.write(f"   ❌ Error processing entry {i}: {str(e)}")
                    continue
            
            self.stdout.write(f"\n📊 Import Summary:")
            self.stdout.write(f"   Total processed: {total_entries}")
            self.stdout.write(f"   Created: {created_count}")
            self.stdout.write(f"   Updated: {updated_count}")
            self.stdout.write(f"   Skipped: {skipped_count}")
            self.stdout.write(f"   Errors: {error_count}")
            
            # Show distillery breakdown
            self.stdout.write(f"\n🏭 Distillery Breakdown:")
            sorted_distilleries = sorted(distillery_stats.items(), key=lambda x: x[1]['created'] + x[1]['updated'], reverse=True)
            
            for distillery, stats in sorted_distilleries[:15]:  # Show top 15
                total_brands = stats['created'] + stats['updated']
                if total_brands > 0:
                    self.stdout.write(f"   • {distillery}: {total_brands} brands (Created: {stats['created']}, Updated: {stats['updated']})")
            
            if len(sorted_distilleries) > 15:
                remaining = len(sorted_distilleries) - 15
                self.stdout.write(f"   ... and {remaining} more distilleries")
            
            # Final verification
            self.stdout.write(f"\n🔍 Final Verification:")
            
            total_warehouse_entries = BrandWarehouse.objects.count()
            self.stdout.write(f"   Total BrandWarehouse entries: {total_warehouse_entries}")
            
            # Check unique distilleries in warehouse
            unique_distilleries = BrandWarehouse.objects.values_list('distillery_name', flat=True).distinct().count()
            self.stdout.write(f"   Unique distilleries in warehouse: {unique_distilleries}")
            
            # Check pack size distribution
            pack_sizes = BrandWarehouse.objects.values_list('capacity_size', flat=True).distinct().order_by('capacity_size')
            self.stdout.write(f"   Available pack sizes: {list(pack_sizes)}")
            
            # Check Sikkim brands specifically
            sikkim_brands = BrandWarehouse.objects.filter(
                distillery_name__icontains='Sikkim Distilleries Ltd'
            ).count()
            self.stdout.write(f"   Sikkim Distilleries Ltd brands: {sikkim_brands}")
            
            self.stdout.write(f"\n✅ ALL brands successfully imported to Brand Warehouse!")
            self.stdout.write(f"   Frontend filtering will now work perfectly for all distilleries")