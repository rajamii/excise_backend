import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouse
from models.transactional.supply_chain.brand_warehouse.production_models import ProductionBatch

# Get a brand warehouse
brand = BrandWarehouse.objects.first()
if brand:
    print(f"Testing with brand: {brand.brand_details} (ID: {brand.id})")
    
    # Check if there are any production batches
    batches = ProductionBatch.objects.filter(brand_warehouse=brand)
    print(f"Production batches found: {batches.count()}")
    
    if batches.exists():
        for batch in batches[:5]:
            print(f"  - {batch.batch_reference}: {batch.quantity_produced} units on {batch.production_date}")
    else:
        print("No production batches found. Creating a test batch...")
        
        # Create a test production batch
        test_batch = ProductionBatch.objects.create(
            brand_warehouse=brand,
            batch_reference=f"TEST-{brand.id}-001",
            quantity_produced=100,
            production_manager="Test Manager",
            status="COMPLETED",
            notes="Test production batch"
        )
        print(f"Created test batch: {test_batch.batch_reference}")
        print(f"Stock before: {test_batch.stock_before}")
        print(f"Stock after: {test_batch.stock_after}")
else:
    print("No brand warehouse entries found!")
