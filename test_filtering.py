#!/usr/bin/env python
"""
Test script to verify filtering shows only Sikkim Distilleries Ltd brands
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouse
from models.transactional.supply_chain.brand_warehouse.services import BrandWarehouseStockService

def test_filtering():
    """Test that filtering only shows Sikkim Distilleries Ltd brands"""
    
    print("🔍 Testing Brand Filtering...")
    
    # Test the service method
    sikkim_brands = BrandWarehouseStockService.get_all_sikkim_brands_with_stock()
    
    print(f"\n📊 Found {sikkim_brands.count()} brands:")
    
    sikkim_distilleries_count = 0
    other_companies_count = 0
    
    for brand in sikkim_brands:
        distillery = brand.distillery_name
        brand_name = brand.brand_details
        
        if "Sikkim Distilleries Ltd" in distillery:
            sikkim_distilleries_count += 1
            print(f"✅ {brand_name} - {distillery}")
        else:
            other_companies_count += 1
            print(f"❌ {brand_name} - {distillery}")
    
    print(f"\n📋 Summary:")
    print(f"   Sikkim Distilleries Ltd brands: {sikkim_distilleries_count}")
    print(f"   Other companies: {other_companies_count}")
    
    if other_companies_count == 0:
        print("✅ Filtering is working correctly - only Sikkim Distilleries Ltd brands shown!")
    else:
        print("❌ Filtering issue - other companies are still being shown")
    
    # Test direct query
    print(f"\n🔍 Direct database query test:")
    all_brands = BrandWarehouse.objects.filter(
        distillery_name__icontains='Sikkim Distilleries Ltd'
    )
    print(f"   Direct query found: {all_brands.count()} brands")
    
    # Show some examples
    print(f"\n📝 Sample brands:")
    for brand in all_brands[:5]:
        print(f"   - {brand.brand_details} ({brand.capacity_size}ml)")

if __name__ == "__main__":
    test_filtering()
    print("🏁 Test completed!")