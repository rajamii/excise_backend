#!/usr/bin/env python
"""
Backfill ProductionBatch records from existing BrandWarehouseArrival records
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouseArrival
from models.transactional.supply_chain.brand_warehouse.production_models import ProductionBatch
from django.utils import timezone

def backfill_production_batches():
    """Create ProductionBatch records for existing arrivals"""
    
    arrivals = BrandWarehouseArrival.objects.filter(
        source_type='HOLOGRAM_REGISTER'
    ).order_by('arrival_date')
    
    print(f"Found {arrivals.count()} hologram register arrivals to backfill")
    
    created_count = 0
    skipped_count = 0
    
    for arrival in arrivals:
        # Check if production batch already exists for this reference
        existing = ProductionBatch.objects.filter(
            source_reference=arrival.reference_no
        ).first()
        
        if existing:
            print(f"⏭️  Skipping {arrival.reference_no} - production batch already exists")
            skipped_count += 1
            continue
        
        # Generate batch reference
        production_date = arrival.arrival_date.date() if hasattr(arrival.arrival_date, 'date') else arrival.arrival_date
        batch_ref = f"PROD-{production_date.strftime('%Y%m%d')}-{arrival.brand_warehouse_id}-{ProductionBatch.objects.filter(production_date=production_date).count() + 1:03d}"
        
        # Create production batch
        production_batch = ProductionBatch(
            brand_warehouse=arrival.brand_warehouse,
            batch_reference=batch_ref,
            source_reference=arrival.reference_no,
            production_date=production_date,
            production_time=arrival.arrival_date.time() if hasattr(arrival.arrival_date, 'time') else timezone.now().time(),
            quantity_produced=arrival.quantity_added,
            stock_before=arrival.previous_stock,
            stock_after=arrival.new_stock,
            production_manager='System',
            status='COMPLETED',
            notes=f"Backfilled from arrival record: {arrival.notes}"
        )
        
        # Save without triggering stock update
        super(ProductionBatch, production_batch).save()
        
        print(f"✅ Created production batch: {batch_ref} for {arrival.reference_no}")
        created_count += 1
    
    print(f"\n📊 Summary:")
    print(f"   Created: {created_count}")
    print(f"   Skipped: {skipped_count}")
    print(f"   Total: {arrivals.count()}")

if __name__ == '__main__':
    backfill_production_batches()
