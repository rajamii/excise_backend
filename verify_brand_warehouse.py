import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouse

def create_sample_data():
    print("Creating sample BrandWarehouse data...")
    try:
        # Clear existing data to avoid confusion (optional, but good for clean state)
        # BrandWarehouse.objects.all().delete()
        
        # Create a new entry
        bw = BrandWarehouse.objects.create(
            distillery_name="Test Distillery",
            brand_type="Whisky",
            brand_details="Test Brand Details",
            capacity_size=750,
            current_stock=100,
            max_capacity=1000,
            status="IN_STOCK"
        )
        print(f"Created BrandWarehouse: {bw} with capacity_size={bw.capacity_size}")

        # Simulate fetching from LiquorData (since we can't easily Mock request here without full setup)
        # This part just confirms we can query keys
        print("Checking LiquorData keys...")
        # from models.masters.supply_chain.liquor_data.models import LiquorData
        # count = LiquorData.objects.count()
        # print(f"Found {count} LiquorData entries")

    except Exception as e:
        print(f"Error creating data: {e}")
        
        bw2 = BrandWarehouse.objects.create(
             distillery_name="Test Distillery",
            brand_type="Whisky",
            brand_details="Test Brand Details",
            capacity_size=375,
            current_stock=50,
            max_capacity=500,
            status="IN_STOCK"
        )
        print(f"Created BrandWarehouse: {bw2} with capacity_size={bw2.capacity_size}")

    except Exception as e:
        print(f"Error creating data: {e}")

if __name__ == '__main__':
    create_sample_data()
