#!/usr/bin/env python
"""
Test script to verify Brand Warehouse stock update logic
"""
import os
import sys
import django

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.transactional.supply_chain.hologram.models import DailyHologramRegister
from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouse, BrandWarehouseArrival
from models.transactional.supply_chain.brand_warehouse.services import BrandWarehouseStockService
from models.masters.supply_chain.profile.models import SupplyChainUserProfile
from datetime import date


def test_brand_warehouse_update():
    """
    Test the Brand Warehouse stock update logic
    """
    print("🧪 Testing Brand Warehouse Stock Update Logic")
    print("=" * 50)
    
    # Test 1: Parse bottle size
    print("\n1. Testing bottle size parsing:")
    test_sizes = ["750ml", "375 ml", "180ML", "750", "1000 ML"]
    for size in test_sizes:
        parsed = BrandWarehouseStockService._parse_bottle_size(size)
        print(f"   {size} -> {parsed}ml")
    
    # Test 2: Check existing Brand Warehouse entries
    print("\n2. Existing Brand Warehouse entries:")
    warehouses = BrandWarehouse.objects.all()[:5]
    for warehouse in warehouses:
        print(f"   {warehouse.distillery_name} - {warehouse.brand_details} ({warehouse.capacity_size}ml)")
        print(f"      Current Stock: {warehouse.current_stock}, Status: {warehouse.status}")
    
    # Test 3: Check Daily Hologram Register entries
    print("\n3. Recent Daily Hologram Register entries:")
    daily_registers = DailyHologramRegister.objects.filter(is_fixed=True)[:5]
    for register in daily_registers:
        print(f"   {register.reference_no} - {register.brand_details} ({register.bottle_size})")
        print(f"      Issued: {register.issued_qty}, Licensee: {register.licensee.manufacturing_unit_name if register.licensee else 'None'}")
    
    # Test 4: Check Brand Warehouse Arrivals
    print("\n4. Recent Brand Warehouse Arrivals:")
    arrivals = BrandWarehouseArrival.objects.all()[:5]
    for arrival in arrivals:
        print(f"   {arrival.reference_no} - {arrival.quantity_added} units")
        print(f"      {arrival.brand_warehouse.distillery_name} - {arrival.brand_warehouse.brand_details}")
        print(f"      Previous: {arrival.previous_stock}, New: {arrival.new_stock}")
    
    print("\n✅ Test completed!")


def simulate_monthly_statement_save():
    """
    Simulate saving a monthly statement and updating brand warehouse
    """
    print("\n🔄 Simulating Monthly Statement Save")
    print("=" * 40)
    
    # Find a Sikkim licensee
    sikkim_licensee = SupplyChainUserProfile.objects.filter(
        manufacturing_unit_name__icontains='sikkim'
    ).first()
    
    if not sikkim_licensee:
        print("❌ No Sikkim licensee found for testing")
        return
    
    print(f"📍 Using licensee: {sikkim_licensee.manufacturing_unit_name}")
    
    # Create a test daily register entry
    test_register = DailyHologramRegister(
        reference_no="TEST-2026-001",
        licensee=sikkim_licensee,
        usage_date=date.today(),
        brand_details="Sikkim Creme-De-Menthe Liquor",
        bottle_size="375ml",
        issued_qty=100,
        is_fixed=True
    )
    
    print(f"📝 Test Monthly Statement:")
    print(f"   Reference: {test_register.reference_no}")
    print(f"   Brand: {test_register.brand_details}")
    print(f"   Size: {test_register.bottle_size}")
    print(f"   Quantity: {test_register.issued_qty}")
    
    # Test the service directly (without saving to avoid duplicate data)
    print(f"\n🔄 Testing stock update service...")
    success = BrandWarehouseStockService.update_stock_from_hologram_register(test_register)
    
    if success:
        print("✅ Stock update service worked successfully!")
        
        # Check if Brand Warehouse was created/updated
        warehouse = BrandWarehouse.objects.filter(
            distillery_name__icontains=sikkim_licensee.manufacturing_unit_name,
            brand_details__icontains="Sikkim Creme-De-Menthe",
            capacity_size=375
        ).first()
        
        if warehouse:
            print(f"📦 Brand Warehouse found:")
            print(f"   Current Stock: {warehouse.current_stock}")
            print(f"   Status: {warehouse.status}")
            
            # Check arrivals
            recent_arrival = warehouse.arrivals.filter(reference_no="TEST-2026-001").first()
            if recent_arrival:
                print(f"📥 Arrival record created:")
                print(f"   Quantity Added: {recent_arrival.quantity_added}")
                print(f"   Previous Stock: {recent_arrival.previous_stock}")
                print(f"   New Stock: {recent_arrival.new_stock}")
        
    else:
        print("❌ Stock update service failed")


if __name__ == "__main__":
    try:
        test_brand_warehouse_update()
        simulate_monthly_statement_save()
    except Exception as e:
        print(f"❌ Error during testing: {str(e)}")
        import traceback
        traceback.print_exc()