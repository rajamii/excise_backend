import os
import django
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouse
from models.masters.supply_chain.liquor_data.models import LiquorData

def import_brands():
    print("Starting Brand Import...")
    
    # 1. Check LiquorData
    total_liquor = LiquorData.objects.count()
    print(f"Found {total_liquor} entries in LiquorData.")
    
    if total_liquor == 0:
        print("Warning: LiquorData is empty. Cannot import brands.")
        return

    # 2. Fetch all entries
    items = LiquorData.objects.values(
        'id',
        'brand_name', 
        'manufacturing_unit_name', 
        'brand_owner', 
        'liquor_type',
        'pack_size_ml'
    )

    created_count = 0
    updated_count = 0
    processed_keys = set()
    
    # 3. Import
    for item in items:
        brand_name = item['brand_name']
        distillery = item['manufacturing_unit_name']
        pack_size = item['pack_size_ml']
        
        if not brand_name or not distillery or not pack_size:
            continue
            
        # Composite key to avoid duplicates in this run
        key = (distillery, brand_name, pack_size)
        if key in processed_keys:
            continue
        processed_keys.add(key)
        
        print(f"Processing: {brand_name} ({pack_size}ml) - {distillery}")
        
        try:
            # Create or update - try to find by distillery + brand + capacity
            # BUT also try to find if there is a '0' capacity one that matches description? 
            # No, we deleted 0s.
            
            # Using update_or_create to force update fields
            obj, created = BrandWarehouse.objects.update_or_create(
                distillery_name=distillery,
                brand_details__icontains=brand_name,
                capacity_size=pack_size,
                defaults={
                    'brand_type': item['liquor_type'] or 'Unknown',
                    'brand_details': f"{brand_name} - {item['brand_owner']}",
                    # Don't reset stock if exists
                    # 'current_stock': 0, 
                    'max_capacity': 10000,
                    'reorder_level': 1000,
                    'average_daily_usage': 0,
                    # 'status': 'OUT_OF_STOCK',
                    'liquor_data_id': item['id']
                }
            )
            
            # Additional check: confirm capacity_size is set (pk check)
            if obj.capacity_size != pack_size:
                obj.capacity_size = pack_size
                obj.save(update_fields=['capacity_size'])
                
            if created:
                created_count += 1
            else:
                updated_count += 1
                
        except Exception as e:
            print(f"Error importing {brand_name}: {e}")
                
        except Exception as e:
            print(f"Error importing {brand_name}: {e}")

    print(f"Import Complete. Created: {created_count}, Updated: {updated_count}")

    # Verify
    zero_cap = BrandWarehouse.objects.filter(capacity_size=0).count()
    if zero_cap > 0:
        print(f"Warning: There are still {zero_cap} entries with capacity_size=0.")
        # Optional: Delete them?
        # BrandWarehouse.objects.filter(capacity_size=0).delete()
        # print("Deleted entries with capacity_size=0")

if __name__ == '__main__':
    import_brands()
