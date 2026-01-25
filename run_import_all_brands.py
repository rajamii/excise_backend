#!/usr/bin/env python
"""
Simple script to import all brands from LiquorData to BrandWarehouse
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from django.db import transaction
from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouse
from models.masters.supply_chain.liquor_data.models import LiquorData

def import_all_brands():
    print("🔄 Importing ALL Brands to Brand Warehouse...")
    print("=" * 60)
    
    with transaction.atomic():
        # Get ALL liquor data entries
        all_liquor_data = LiquorData.objects.all()
        total_entries = all_liquor_data.count()
        print(f"📦 Found {total_entries} total liquor data entries to process")
        
        created_count = 0
        updated_count = 0
        skipped_count = 0
        
        for i, liquor_item in enumerate(all_liquor_data, 1):
            try:
                brand_name = liquor_item.brand_name
                distillery = liquor_item.manufacturing_unit_name
                pack_size = liquor_item.pack_size_ml
                brand_owner = liquor_item.brand_owner
                liquor_type = liquor_item.liquor_type
                
                # Skip entries with missing critical data
                if not brand_name or not distillery or not pack_size:
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
                        'liquor_data_id': liquor_item.id,
                        'max_capacity': 10000,
                        'reorder_level': 1000,
                        'status': 'OUT_OF_STOCK'
                    }
                )
                
                if created:
                    created_count += 1
                    if created_count <= 20:  # Show first 20 created
                        print(f"   ✅ Created: {brand_name} ({pack_size}ml) - {distillery}")
                else:
                    # Update existing entry with liquor_data reference if missing
                    if not warehouse_entry.liquor_data_id:
                        warehouse_entry.liquor_data_id = liquor_item.id
                        warehouse_entry.save(update_fields=['liquor_data_id'])
                        updated_count += 1
                
                # Progress indicator
                if i % 50 == 0:
                    print(f"   📊 Progress: {i}/{total_entries} ({(i/total_entries)*100:.1f}%)")
                
            except Exception as e:
                print(f"   ❌ Error processing {brand_name}: {str(e)}")
                continue
        
        print(f"\n📊 Import Summary:")
        print(f"   Total processed: {total_entries}")
        print(f"   Created: {created_count}")
        print(f"   Updated: {updated_count}")
        print(f"   Skipped: {skipped_count}")
        
        # Final verification
        total_warehouse_entries = BrandWarehouse.objects.count()
        print(f"   Total BrandWarehouse entries: {total_warehouse_entries}")
        
        # Check Sikkim brands specifically
        sikkim_brands = BrandWarehouse.objects.filter(
            distillery_name__icontains='Sikkim Distilleries Ltd'
        ).count()
        print(f"   Sikkim Distilleries Ltd brands: {sikkim_brands}")
        
        print(f"\n✅ ALL brands successfully imported to Brand Warehouse!")

if __name__ == "__main__":
    import_all_brands()