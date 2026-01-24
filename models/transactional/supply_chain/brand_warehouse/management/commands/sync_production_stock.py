from django.core.management.base import BaseCommand
from django.apps import apps
from django.db import transaction
from django.utils import timezone
from datetime import timedelta


class Command(BaseCommand):
    help = 'Sync production batches with brand warehouse stock to fix any inconsistencies'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Number of days to look back for production batches (default: 30)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes'
        )
        parser.add_argument(
            '--brand-id',
            type=int,
            help='Sync only specific brand warehouse ID'
        )

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']
        brand_id = options.get('brand_id')
        
        self.stdout.write(f"🔄 Syncing production stock for last {days} days...")
        if dry_run:
            self.stdout.write("🔍 DRY RUN MODE - No changes will be made")
        
        # Get models
        BrandWarehouse = apps.get_model('brand_warehouse', 'BrandWarehouse')
        ProductionBatch = apps.get_model('brand_warehouse', 'ProductionBatch')
        
        # Get date range
        start_date = timezone.now().date() - timedelta(days=days)
        
        # Get brand warehouses to sync
        if brand_id:
            brand_warehouses = BrandWarehouse.objects.filter(id=brand_id)
        else:
            brand_warehouses = BrandWarehouse.objects.filter(
                distillery_name__icontains='sikkim'
            )
        
        total_synced = 0
        total_errors = 0
        
        for brand_warehouse in brand_warehouses:
            try:
                self.stdout.write(f"\n📦 Processing: {brand_warehouse.brand_details} ({brand_warehouse.capacity_size}ml)")
                
                # Get all production batches for this brand in the date range
                production_batches = ProductionBatch.objects.filter(
                    brand_warehouse=brand_warehouse,
                    production_date__gte=start_date
                ).order_by('production_date', 'created_at')
                
                if not production_batches.exists():
                    self.stdout.write(f"   ⚪ No production batches found")
                    continue
                
                # Calculate expected stock from production batches
                initial_stock = 0  # We'll calculate from the earliest batch
                expected_stock = initial_stock
                
                for batch in production_batches:
                    expected_stock += batch.quantity_produced
                    self.stdout.write(f"   📅 {batch.production_date}: +{batch.quantity_produced} units (batch: {batch.batch_reference})")
                
                current_stock = brand_warehouse.current_stock
                
                self.stdout.write(f"   📊 Current stock: {current_stock}")
                self.stdout.write(f"   📊 Expected from production: {expected_stock}")
                
                if current_stock != expected_stock:
                    self.stdout.write(f"   ⚠️  Stock mismatch detected!")
                    
                    if not dry_run:
                        with transaction.atomic():
                            # Update the brand warehouse stock
                            old_stock = brand_warehouse.current_stock
                            brand_warehouse.current_stock = expected_stock
                            brand_warehouse.save(update_fields=['current_stock', 'updated_at'])
                            brand_warehouse.update_status()
                            
                            self.stdout.write(f"   ✅ Updated stock: {old_stock} → {expected_stock}")
                            total_synced += 1
                    else:
                        self.stdout.write(f"   🔍 Would update stock: {current_stock} → {expected_stock}")
                        total_synced += 1
                else:
                    self.stdout.write(f"   ✅ Stock is already correct")
                    
            except Exception as e:
                self.stdout.write(f"   ❌ Error processing {brand_warehouse.brand_details}: {str(e)}")
                total_errors += 1
        
        # Summary
        self.stdout.write(f"\n📋 Sync Summary:")
        self.stdout.write(f"   Brands processed: {brand_warehouses.count()}")
        self.stdout.write(f"   Stocks synced: {total_synced}")
        self.stdout.write(f"   Errors: {total_errors}")
        
        if dry_run:
            self.stdout.write(f"\n🔍 This was a dry run. Use --no-dry-run to apply changes.")
        else:
            self.stdout.write(f"\n✅ Sync completed successfully!")