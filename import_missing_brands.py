#!/usr/bin/env python
"""
Import the 4 missing brand entries that were skipped during the initial import
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from django.db import transaction
from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouse
from models.masters.supply_chain.liquor_data.models import LiquorData

def import_missing_brands():
    print("🔄 Importing Missing Brand Entries...")
    print("=" * 50)
    
    # The 4 missing IDs we found
    missing_ids = [197, 198, 199, 231]
    
    with transaction.atomic():
        created_count = 0
        
        for liquor_id in missing_ids:
            try:
                liquor_item = LiquorData.objects.get(id=liquor_id)
                
                brand_name = liquor_item.brand_name
                distillery = liquor_item.manufacturing_unit_name
                pack_size = liquor_item.pack_size_ml
                brand_owner = liquor_item.brand_owner
                liquor_type = liquor_item.liquor_type
                
                print(f"Processing: {brand_name} ({pack_size}ml) - {distillery}")
                
                # Create brand details string
                if brand_owner and brand_owner != brand_name:
                    brand_details = f"{brand_name} - {brand_owner}"
                else:
                    brand_details = brand_name
                
                # Create Brand Warehouse entry
                warehouse_entry, created = BrandWarehouse.objects.get_or_create(
                    distillery_name=distillery,
                    brand_details=brand_details,
                    capacity_size=pack_size,
                    defaults={
                        'brand_type': liquor_type or 'Beer' if 'beer' in brand_name.lower() else 'Liquor',
                        'current_stock': 0,
                        'liquor_data_id': liquor_item.id,
                        'max_capacity': 10000,
                        'reorder_level': 1000,
                        'status': 'OUT_OF_STOCK'
                    }
                )
                
                if created:
                    created_count += 1
                    print(f"   ✅ Created: {brand_name} ({pack_size}ml)")
                else:
                    print(f"   ⚠️ Already exists: {brand_name} ({pack_size}ml)")
                
            except LiquorData.DoesNotExist:
                print(f"   ❌ LiquorData ID {liquor_id} not found")
            except Exception as e:
                print(f"   ❌ Error processing ID {liquor_id}: {str(e)}")
        
        print(f"\n📊 Import Summary:")
        print(f"   Missing entries processed: {len(missing_ids)}")
        print(f"   Successfully created: {created_count}")
        
        # Verify final counts
        total_warehouse = BrandWarehouse.objects.count()
        total_liquor = LiquorData.objects.count()
        
        print(f"\n🔍 Final Verification:")
        print(f"   LiquorData entries: {total_liquor}")
        print(f"   BrandWarehouse entries: {total_warehouse}")
        
        if total_warehouse >= total_liquor:
            print(f"   ✅ SUCCESS: All entries now imported!")
        else:
            missing = total_liquor - total_warehouse
            print(f"   ⚠️ Still missing: {missing} entries")

if __name__ == "__main__":
    import_missing_brands()