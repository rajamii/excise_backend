#!/usr/bin/env python
"""
Script to restore brand warehouse data after accidental deletion
"""
import os
import sys
import django

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouse, BrandWarehouseArrival
from models.transactional.supply_chain.brand_warehouse.services import BrandWarehouseStockService
from models.transactional.supply_chain.hologram.models import DailyHologramRegister
from models.masters.supply_chain.liquor_data.models import LiquorData
from django.db import transaction
import logging

logger = logging.getLogger(__name__)


def restore_brand_warehouse_data():
    """
    Restore brand warehouse data by:
    1. Re-creating all Sikkim Distilleries Ltd brand entries
    2. Recalculating stock from existing daily register entries
    3. Recreating arrival records
    """
    print("🔄 Restoring Brand Warehouse Data...")
    print("=" * 60)
    
    with transaction.atomic():
        # Step 1: Re-create all Sikkim brand warehouse entries
        print("\n📦 Step 1: Re-creating brand warehouse entries...")
        
        # Get all Sikkim Distilleries Ltd liquor data
        sikkim_liquor_data = LiquorData.objects.filter(
            manufacturing_unit_name__icontains='Sikkim Distilleries Ltd'
        ).values(
            'id', 'brand_name', 'manufacturing_unit_name', 
            'brand_owner', 'liquor_type', 'pack_size_ml'
        )
        
        created_count = 0
        
        for item in sikkim_liquor_data:
            brand_name = item['brand_name']
            distillery = item['manufacturing_unit_name']
            pack_size = item['pack_size_ml']
            
            if not brand_name or not distillery or not pack_size:
                continue
            
            # Create Brand Warehouse entry
            warehouse_entry, created = BrandWarehouse.objects.get_or_create(
                distillery_name=distillery,
                brand_details=f"{brand_name} - {item['brand_owner']}",
                capacity_size=pack_size,
                defaults={
                    'brand_type': item['liquor_type'] or 'Liquor',
                    'current_stock': 0,  # Will be recalculated
                    'liquor_data_id': item['id'],
                    'max_capacity': 10000,
                    'reorder_level': 1000,
                    'status': 'OUT_OF_STOCK'
                }
            )
            
            if created:
                created_count += 1
                print(f"   ✅ Created: {brand_name} ({pack_size}ml)")
        
        print(f"\n📊 Created {created_count} brand warehouse entries")
        
        # Step 2: Recalculate stock from daily register entries
        print("\n🔄 Step 2: Recalculating stock from daily register entries...")
        
        # Get all fixed daily register entries for Sikkim Distilleries Ltd
        daily_entries = DailyHologramRegister.objects.filter(
            is_fixed=True,
            issued_qty__gt=0,
            licensee__manufacturing_unit_name__icontains='Sikkim Distilleries Ltd'
        ).order_by('usage_date', 'created_at')
        
        print(f"   Found {daily_entries.count()} daily register entries to process")
        
        stock_updates = 0
        arrival_records = 0
        
        for entry in daily_entries:
            try:
                # Parse bottle size
                capacity_ml = BrandWarehouseStockService._parse_bottle_size(entry.bottle_size)
                if not capacity_ml:
                    continue
                
                # Find matching warehouse entry
                warehouse = BrandWarehouse.objects.filter(
                    distillery_name__icontains=entry.licensee.manufacturing_unit_name,
                    brand_details__icontains=entry.brand_details,
                    capacity_size=capacity_ml
                ).first()
                
                if not warehouse:
                    # Create warehouse entry if not found
                    warehouse = BrandWarehouse.objects.create(
                        distillery_name=entry.licensee.manufacturing_unit_name,
                        brand_details=entry.brand_details,
                        brand_type='Liquor',
                        capacity_size=capacity_ml,
                        current_stock=0,
                        max_capacity=10000,
                        reorder_level=1000,
                        status='OUT_OF_STOCK'
                    )
                    print(f"   📦 Created missing warehouse: {entry.brand_details} ({capacity_ml}ml)")
                
                # Check if arrival record already exists
                existing_arrival = BrandWarehouseArrival.objects.filter(
                    brand_warehouse=warehouse,
                    reference_no=entry.reference_no,
                    quantity_added=entry.issued_qty
                ).first()
                
                if not existing_arrival:
                    # Update stock
                    previous_stock = warehouse.current_stock
                    warehouse.current_stock += entry.issued_qty
                    warehouse.save()
                    
                    # Create arrival record
                    BrandWarehouseArrival.objects.create(
                        brand_warehouse=warehouse,
                        reference_no=entry.reference_no,
                        source_type='HOLOGRAM_REGISTER',
                        quantity_added=entry.issued_qty,
                        previous_stock=previous_stock,
                        new_stock=warehouse.current_stock,
                        arrival_date=entry.created_at or entry.usage_date,
                        notes=f"Restored: {entry.brand_details} ({entry.bottle_size}) - {entry.usage_date}"
                    )
                    
                    stock_updates += 1
                    arrival_records += 1
                    
                    print(f"   ✅ Updated: {entry.brand_details} +{entry.issued_qty} = {warehouse.current_stock}")
                
            except Exception as e:
                print(f"   ❌ Error processing entry {entry.reference_no}: {str(e)}")
                continue
        
        print(f"\n📊 Restoration Summary:")
        print(f"   Stock updates: {stock_updates}")
        print(f"   Arrival records: {arrival_records}")
        
        # Step 3: Update warehouse statuses
        print("\n🔄 Step 3: Updating warehouse statuses...")
        
        warehouses = BrandWarehouse.objects.filter(
            distillery_name__icontains='Sikkim Distilleries Ltd'
        )
        
        for warehouse in warehouses:
            warehouse.update_status()
        
        print(f"   ✅ Updated {warehouses.count()} warehouse statuses")
        
        # Step 4: Show final summary
        print("\n📊 Final Summary:")
        
        total_warehouses = BrandWarehouse.objects.filter(
            distillery_name__icontains='Sikkim Distilleries Ltd'
        ).count()
        
        total_stock = BrandWarehouse.objects.filter(
            distillery_name__icontains='Sikkim Distilleries Ltd'
        ).aggregate(total=models.Sum('current_stock'))['total'] or 0
        
        in_stock = BrandWarehouse.objects.filter(
            distillery_name__icontains='Sikkim Distilleries Ltd',
            status='IN_STOCK'
        ).count()
        
        low_stock = BrandWarehouse.objects.filter(
            distillery_name__icontains='Sikkim Distilleries Ltd',
            status='LOW_STOCK'
        ).count()
        
        out_of_stock = BrandWarehouse.objects.filter(
            distillery_name__icontains='Sikkim Distilleries Ltd',
            status='OUT_OF_STOCK'
        ).count()
        
        print(f"   Total Warehouses: {total_warehouses}")
        print(f"   Total Stock: {total_stock} units")
        print(f"   In Stock: {in_stock}")
        print(f"   Low Stock: {low_stock}")
        print(f"   Out of Stock: {out_of_stock}")
        
        print(f"\n✅ Brand Warehouse data successfully restored!")


if __name__ == "__main__":
    try:
        # Import models here to avoid circular imports
        from django.db import models
        restore_brand_warehouse_data()
    except Exception as e:
        print(f"❌ Error during restoration: {str(e)}")
        import traceback
        traceback.print_exc()