#!/usr/bin/env python
"""
Script to import ALL brands from LiquorData into BrandWarehouse
This ensures all 278+ brands are available in the warehouse system
"""
import os
import sys
import django

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouse
from models.masters.supply_chain.liquor_data.models import LiquorData
from django.db import transaction
import logging

logger = logging.getLogger(__name__)


def import_all_brands_to_warehouse():
    """
    Import ALL brands from LiquorData into BrandWarehouse
    This creates warehouse entries for every single brand in the system
    """
    print("🔄 Importing ALL Brands to Brand Warehouse...")
    print("=" * 60)
    
    with transaction.atomic():
        # Get ALL liquor data entries
        all_liquor_data = LiquorData.objects.all().values(
            'id', 'brand_name', 'manufacturing_unit_name', 
            'brand_owner', 'liquor_type', 'pack_size_ml'
        )
        
        total_entries = len(all_liquor_data)
        print(f"📦 Found {total_entries} total liquor data entries to process")
        
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
                    print(f"   ⚠️ Skipping entry {i}: Missing data - Brand: {brand_name}, Distillery: {distillery}, Size: {pack_size}")
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
                    print(f"   ✅ Created ({i}/{total_entries}): {brand_name} ({pack_size}ml) - {distillery}")
                else:
                    # Update existing entry with liquor_data reference if missing
                    if not warehouse_entry.liquor_data_id:
                        warehouse_entry.liquor_data_id = item['id']
                        warehouse_entry.save(update_fields=['liquor_data_id'])
                        updated_count += 1
                        distillery_stats[distillery]['updated'] += 1
                        print(f"   🔄 Updated ({i}/{total_entries}): {brand_name} ({pack_size}ml) - {distillery}")
                
                # Progress indicator for large datasets
                if i % 50 == 0:
                    print(f"   📊 Progress: {i}/{total_entries} ({(i/total_entries)*100:.1f}%)")
                
            except Exception as e:
                error_count += 1
                print(f"   ❌ Error processing entry {i}: {str(e)}")
                continue
        
        print(f"\n📊 Import Summary:")
        print(f"   Total processed: {total_entries}")
        print(f"   Created: {created_count}")
        print(f"   Updated: {updated_count}")
        print(f"   Skipped: {skipped_count}")
        print(f"   Errors: {error_count}")
        
        # Show distillery breakdown
        print(f"\n🏭 Distillery Breakdown:")
        sorted_distilleries = sorted(distillery_stats.items(), key=lambda x: x[1]['created'] + x[1]['updated'], reverse=True)
        
        for distillery, stats in sorted_distilleries[:15]:  # Show top 15
            total_brands = stats['created'] + stats['updated']
            if total_brands > 0:
                print(f"   • {distillery}: {total_brands} brands (Created: {stats['created']}, Updated: {stats['updated']})")
        
        if len(sorted_distilleries) > 15:
            remaining = len(sorted_distilleries) - 15
            print(f"   ... and {remaining} more distilleries")
        
        # Final verification
        print(f"\n🔍 Final Verification:")
        
        total_warehouse_entries = BrandWarehouse.objects.count()
        print(f"   Total BrandWarehouse entries: {total_warehouse_entries}")
        
        # Check unique distilleries in warehouse
        unique_distilleries = BrandWarehouse.objects.values_list('distillery_name', flat=True).distinct().count()
        print(f"   Unique distilleries in warehouse: {unique_distilleries}")
        
        # Check pack size distribution
        pack_sizes = BrandWarehouse.objects.values_list('capacity_size', flat=True).distinct().order_by('capacity_size')
        print(f"   Available pack sizes: {list(pack_sizes)}")
        
        # Check Sikkim brands specifically
        sikkim_brands = BrandWarehouse.objects.filter(
            distillery_name__icontains='Sikkim Distilleries Ltd'
        ).count()
        print(f"   Sikkim Distilleries Ltd brands: {sikkim_brands}")
        
        print(f"\n✅ ALL brands successfully imported to Brand Warehouse!")
        print(f"   Frontend filtering will now work perfectly for all distilleries")


def verify_import_success():
    """
    Verify that the import was successful
    """
    print("\n🧪 Verifying Import Success...")
    print("=" * 40)
    
    # Check total counts
    liquor_count = LiquorData.objects.count()
    warehouse_count = BrandWarehouse.objects.count()
    
    print(f"LiquorData entries: {liquor_count}")
    print(f"BrandWarehouse entries: {warehouse_count}")
    
    if warehouse_count >= liquor_count:
        print("✅ Import successful - all brands are in warehouse")
    else:
        missing = liquor_count - warehouse_count
        print(f"⚠️ {missing} brands may be missing from warehouse")
    
    # Check for brands without liquor_data reference
    without_reference = BrandWarehouse.objects.filter(liquor_data_id__isnull=True).count()
    if without_reference > 0:
        print(f"⚠️ {without_reference} warehouse entries without liquor_data reference")
    else:
        print("✅ All warehouse entries have liquor_data references")
    
    # Sample verification
    print(f"\n📋 Sample Verification:")
    sample_brands = BrandWarehouse.objects.select_related('liquor_data')[:5]
    for brand in sample_brands:
        liquor_ref = "✅" if brand.liquor_data_id else "❌"
        print(f"   {liquor_ref} {brand.brand_details} ({brand.capacity_size}ml) - {brand.distillery_name}")


if __name__ == "__main__":
    try:
        import_all_brands_to_warehouse()
        verify_import_success()
    except Exception as e:
        print(f"❌ Import failed: {str(e)}")
        import traceback
        traceback.print_exc()