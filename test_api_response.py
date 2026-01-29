#!/usr/bin/env python
"""
Test script to check what the brand warehouse API returns
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouse
from models.transactional.supply_chain.brand_warehouse.serializers import BrandWarehouseSummarySerializer

def test_api_response():
    """Test what the API returns for Sikkim Juniper Gin"""
    
    # Find Sikkim Juniper Gin 750ml
    try:
        brand_warehouse = BrandWarehouse.objects.get(
            brand_details__icontains='Sikkim Juniper Gin',
            capacity_size=750
        )
        print(f"✅ Found brand: {brand_warehouse.brand_details}")
        print(f"   ID: {brand_warehouse.id}")
        print(f"   Current stock (direct): {brand_warehouse.current_stock}")
        print(f"   Status: {brand_warehouse.status}")
        print(f"   Last updated: {brand_warehouse.updated_at}")
        
        # Test serializer
        serializer = BrandWarehouseSummarySerializer(brand_warehouse)
        data = serializer.data
        
        print(f"\n📡 API Response:")
        print(f"   Current stock (API): {data.get('current_stock', 'NOT FOUND')}")
        print(f"   Status (API): {data.get('status', 'NOT FOUND')}")
        print(f"   Pack size (API): {data.get('pack_size_details', {}).get('current_stock', 'NOT FOUND')}")
        
        # Check if there's a mismatch
        if data.get('current_stock') != brand_warehouse.current_stock:
            print("❌ MISMATCH: API response doesn't match database!")
        else:
            print("✅ API response matches database")
            
    except BrandWarehouse.DoesNotExist:
        print("❌ Sikkim Juniper Gin 750ml not found in brand warehouse")
        return
    
    # Also test the list endpoint behavior
    print(f"\n📋 Testing list endpoint...")
    all_sikkim_brands = BrandWarehouse.objects.filter(
        distillery_name__icontains='sikkim',
        brand_details__icontains='Sikkim Juniper Gin',
        capacity_size=750
    )
    
    for brand in all_sikkim_brands:
        serializer = BrandWarehouseSummarySerializer(brand)
        data = serializer.data
        print(f"   Brand: {data.get('brand_name', 'Unknown')}")
        print(f"   Stock: {data.get('current_stock', 'Unknown')}")

if __name__ == "__main__":
    print("🧪 Testing API Response...")
    test_api_response()
    print("🏁 Test completed!")