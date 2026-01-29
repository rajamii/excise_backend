#!/usr/bin/env python
"""
Fix duplicate stock entries for Sikkim Juniper Gin
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from django.apps import apps
from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouse, BrandWarehouseArrival
from models.transactional.supply_chain.hologram.models import DailyHologramRegister

def fix_duplicate_stock():
    """Fix duplicate stock entries"""
    
    # Find Sikkim Juniper Gin 750ml
    try:
        brand_warehouse = BrandWarehouse.objects.get(
            brand_details__icontains='Sikkim Juniper Gin',
            capacity_size=750
        )
        print(f"✅ Found brand: {brand_warehouse.brand_details}")
        print(f"   Current stock (incorrect): {brand_warehouse.current_stock}")
        
    except BrandWarehouse.DoesNotExist:
        print("❌ Sikkim Juniper Gin 750ml not found")
        return
    
    # Get the hologram register entry
    hologram_entry = DailyHologramRegister.objects.filter(
        brand_details__icontains='Sikkim Juniper Gin',
        bottle_size__icontains='750',
        reference_no='HRQ/2026/70425D'
    ).first()
    
    if hologram_entry:
        print(f"✅ Found hologram entry: {hologram_entry.reference_no}")
        print(f"   Issued quantity: {hologram_entry.issued_qty}")
        print(f"   Usage date: {hologram_entry.usage_date}")
        print(f"   Is fixed: {hologram_entry.is_fixed}")
    
    # Check arrival records
    arrivals = BrandWarehouseArrival.objects.filter(
        brand_warehouse=brand_warehouse,
        reference_no='HRQ/2026/70425D'
    ).order_by('created_at')
    
    print(f"\n📦 Found {arrivals.count()} arrival records:")
    for i, arrival in enumerate(arrivals):
        print(f"   {i+1}. {arrival.created_at}: +{arrival.quantity_added} units")
    
    # Remove duplicate arrivals (keep only the first one)
    if arrivals.count() > 1:
        print(f"\n🧹 Removing {arrivals.count() - 1} duplicate arrival records...")
        duplicates = arrivals[1:]  # Keep first, remove rest
        for duplicate in duplicates:
            print(f"   Removing: {duplicate.created_at} (+{duplicate.quantity_added} units)")
            duplicate.delete()
    
    # Remove test production batch if it exists
    ProductionBatch = apps.get_model('brand_warehouse', 'ProductionBatch')
    test_batches = ProductionBatch.objects.filter(
        brand_warehouse=brand_warehouse,
        batch_reference__startswith='TEST-'
    )
    
    if test_batches.exists():
        print(f"\n🧹 Removing {test_batches.count()} test production batches...")
        for batch in test_batches:
            print(f"   Removing: {batch.batch_reference} (+{batch.quantity_produced} units)")
            test_batches.delete()
    
    # Reset stock to correct amount (should be 3 units from the single hologram entry)
    correct_stock = hologram_entry.issued_qty if hologram_entry else 0
    print(f"\n🔧 Resetting stock to correct amount: {correct_stock} units")
    
    brand_warehouse.current_stock = correct_stock
    brand_warehouse.save(update_fields=['current_stock', 'updated_at'])
    brand_warehouse.update_status()
    
    print(f"✅ Stock corrected!")
    print(f"   New stock: {brand_warehouse.current_stock}")
    print(f"   Status: {brand_warehouse.status}")
    
    # Verify final state
    remaining_arrivals = BrandWarehouseArrival.objects.filter(
        brand_warehouse=brand_warehouse
    ).count()
    print(f"   Remaining arrival records: {remaining_arrivals}")

if __name__ == "__main__":
    print("🔧 Fixing duplicate stock entries...")
    fix_duplicate_stock()
    print("🏁 Fix completed!")