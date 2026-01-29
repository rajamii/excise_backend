#!/usr/bin/env python
"""
Test script to create a production batch and verify stock update
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from django.apps import apps
from django.utils import timezone
from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouse

def test_production_batch():
    """Test creating a production batch and verifying stock update"""
    
    # Get models
    ProductionBatch = apps.get_model('brand_warehouse', 'ProductionBatch')
    
    # Find Sikkim Juniper Gin 750ml
    try:
        brand_warehouse = BrandWarehouse.objects.get(
            brand_details__icontains='Sikkim Juniper Gin',
            capacity_size=750
        )
        print(f"✅ Found brand: {brand_warehouse.brand_details} ({brand_warehouse.capacity_size}ml)")
        print(f"   Current stock: {brand_warehouse.current_stock}")
        
    except BrandWarehouse.DoesNotExist:
        print("❌ Sikkim Juniper Gin 750ml not found in brand warehouse")
        return
    
    # Create a test production batch
    production_batch = ProductionBatch.objects.create(
        brand_warehouse=brand_warehouse,
        batch_reference=f"TEST-{timezone.now().strftime('%Y%m%d-%H%M%S')}",
        production_date=timezone.now().date(),
        production_time=timezone.now().time(),
        quantity_produced=3,  # Same as your production
        production_manager="Test Manager",
        notes="Test production batch to verify stock update"
    )
    
    print(f"✅ Created production batch: {production_batch.batch_reference}")
    print(f"   Quantity produced: {production_batch.quantity_produced}")
    print(f"   Stock before: {production_batch.stock_before}")
    print(f"   Stock after: {production_batch.stock_after}")
    
    # Refresh brand warehouse from database
    brand_warehouse.refresh_from_db()
    print(f"   Brand warehouse current stock: {brand_warehouse.current_stock}")
    print(f"   Brand warehouse status: {brand_warehouse.status}")
    
    if brand_warehouse.current_stock == production_batch.stock_after:
        print("✅ Stock update successful!")
    else:
        print("❌ Stock update failed!")
    
    return production_batch

if __name__ == "__main__":
    print("🧪 Testing Production Batch Creation...")
    test_production_batch()
    print("🏁 Test completed!")