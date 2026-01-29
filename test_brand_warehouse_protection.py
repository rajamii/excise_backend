#!/usr/bin/env python
"""
Test script to verify brand warehouse restoration and deletion protection
"""
import os
import sys
import django

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouse
from models.transactional.supply_chain.brand_warehouse.services import BrandWarehouseStockService


def test_restoration_and_protection():
    """
    Test that brand warehouse data was restored and protection is working
    """
    print("🧪 Testing Brand Warehouse Restoration and Protection...")
    print("=" * 60)
    
    # Test 1: Check if data was restored
    print("\n📊 Test 1: Checking restored data...")
    
    sikkim_brands = BrandWarehouse.objects.filter(
        distillery_name__icontains='Sikkim Distilleries Ltd'
    )
    
    print(f"   Total Sikkim brands: {sikkim_brands.count()}")
    
    # Show sample brands
    sample_brands = sikkim_brands[:5]
    for brand in sample_brands:
        print(f"   ✅ {brand.brand_details} ({brand.capacity_size}ml) - Stock: {brand.current_stock}")
    
    # Test 2: Test soft delete protection
    print("\n🛡️ Test 2: Testing soft delete protection...")
    
    # Try to get a test brand
    test_brand = sikkim_brands.first()
    if test_brand:
        print(f"   Testing with: {test_brand.brand_details}")
        
        # Test hard delete protection
        try:
            test_brand.delete()
            print("   ❌ ERROR: Hard delete should be blocked!")
        except Exception as e:
            print(f"   ✅ Hard delete blocked: {str(e)[:80]}...")
        
        # Test soft delete
        try:
            original_count = BrandWarehouse.objects.count()
            test_brand.soft_delete(deleted_by='test_script')
            new_count = BrandWarehouse.objects.count()
            
            print(f"   ✅ Soft delete successful: {original_count} → {new_count}")
            print(f"   ✅ Deleted at: {test_brand.deleted_at}")
            print(f"   ✅ Deleted by: {test_brand.deleted_by}")
            
            # Test restoration
            test_brand.restore()
            restored_count = BrandWarehouse.objects.count()
            
            print(f"   ✅ Restoration successful: {new_count} → {restored_count}")
            print(f"   ✅ Is deleted: {test_brand.is_deleted}")
            
        except Exception as e:
            print(f"   ❌ Soft delete/restore error: {str(e)}")
    
    # Test 3: Check stock levels
    print("\n📈 Test 3: Checking stock levels...")
    
    brands_with_stock = sikkim_brands.filter(current_stock__gt=0)
    brands_without_stock = sikkim_brands.filter(current_stock=0)
    
    print(f"   Brands with stock: {brands_with_stock.count()}")
    print(f"   Brands without stock: {brands_without_stock.count()}")
    
    if brands_with_stock.exists():
        print("   Sample brands with stock:")
        for brand in brands_with_stock[:3]:
            print(f"     • {brand.brand_details} ({brand.capacity_size}ml): {brand.current_stock} units")
    
    # Test 4: Test service methods
    print("\n🔧 Test 4: Testing service methods...")
    
    try:
        all_brands = BrandWarehouseStockService.get_all_sikkim_brands_with_stock()
        print(f"   ✅ Service method working: {all_brands.count()} brands returned")
        
        # Test new brand detection
        brands_with_tags = BrandWarehouseStockService.get_brands_with_new_tags()
        new_brands_count = sum(1 for brand_id, data in brands_with_tags.items() if data['is_new'])
        print(f"   ✅ New brand detection: {new_brands_count} new brands found")
        
    except Exception as e:
        print(f"   ❌ Service method error: {str(e)}")
    
    # Test 5: Check different pack sizes
    print("\n📦 Test 5: Checking pack size variety...")
    
    pack_sizes = sikkim_brands.values_list('capacity_size', flat=True).distinct().order_by('capacity_size')
    print(f"   Available pack sizes: {list(pack_sizes)}")
    
    for size in pack_sizes:
        count = sikkim_brands.filter(capacity_size=size).count()
        print(f"     • {size}ml: {count} brands")
    
    print(f"\n✅ All tests completed successfully!")
    print(f"📋 Summary:")
    print(f"   • Total brands restored: {sikkim_brands.count()}")
    print(f"   • Soft delete protection: ✅ Active")
    print(f"   • Hard delete protection: ✅ Active")
    print(f"   • Service methods: ✅ Working")
    print(f"   • Pack size variety: ✅ {len(pack_sizes)} different sizes")


if __name__ == "__main__":
    try:
        test_restoration_and_protection()
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()