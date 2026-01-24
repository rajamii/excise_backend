from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from .models import BrandWarehouse, BrandWarehouseArrival
from models.masters.supply_chain.liquor_data.models import LiquorData
import logging

logger = logging.getLogger(__name__)


class BrandWarehouseStockService:
    """
    Service to handle Brand Warehouse stock updates from Monthly Statement of Hologram
    """
    
    @staticmethod
    def get_all_sikkim_brands_with_stock():
        """
        Get ALL Sikkim Distilleries Ltd brands from LiquorData and ensure they have Brand Warehouse entries
        This ensures no brands go missing - all brands are always shown
        
        Returns:
            QuerySet of BrandWarehouse entries for Sikkim Distilleries Ltd brands only
        """
        try:
            # Get only Sikkim Distilleries Ltd liquor data entries (not other Sikkim-based companies)
            sikkim_liquor_data = LiquorData.objects.filter(
                manufacturing_unit_name__icontains='Sikkim Distilleries Ltd'
            ).values(
                'id', 'brand_name', 'manufacturing_unit_name', 
                'brand_owner', 'liquor_type', 'pack_size_ml'
            )
            
            created_count = 0
            
            # Ensure Brand Warehouse entry exists for each Sikkim Distilleries Ltd brand
            for item in sikkim_liquor_data:
                brand_name = item['brand_name']
                distillery = item['manufacturing_unit_name']
                pack_size = item['pack_size_ml']
                
                if not brand_name or not distillery or not pack_size:
                    continue
                
                # Get or create Brand Warehouse entry
                warehouse_entry, created = BrandWarehouse.objects.get_or_create(
                    distillery_name__iexact=distillery,
                    brand_details__icontains=brand_name,
                    capacity_size=pack_size,
                    defaults={
                        'distillery_name': distillery,
                        'brand_type': item['liquor_type'] or 'Liquor',
                        'brand_details': f"{brand_name} - {item['brand_owner']}",
                        'current_stock': 0,
                        'capacity_size': pack_size,
                        'liquor_data_id': item['id'],
                        'max_capacity': 10000,  # Default capacity
                        'reorder_level': 1000,  # Default reorder level
                        'status': 'OUT_OF_STOCK'
                    }
                )
                
                if created:
                    created_count += 1
                    logger.info(f"Created Brand Warehouse entry for: {brand_name} ({pack_size}ml)")
            
            if created_count > 0:
                logger.info(f"Created {created_count} new Brand Warehouse entries")
            
            # Return only Sikkim Distilleries Ltd Brand Warehouse entries
            return BrandWarehouse.objects.filter(
                distillery_name__icontains='Sikkim Distilleries Ltd'
            ).select_related('liquor_data').prefetch_related('arrivals', 'utilizations')
            
        except Exception as e:
            logger.error(f"Error getting Sikkim brands: {str(e)}")
            return BrandWarehouse.objects.none()
    
    @staticmethod
    def update_stock_from_hologram_register(daily_register_entry):
        """
        Update Brand Warehouse current_stock when Daily Hologram Register is saved
        
        This updates the stock for Sikkim Distillery brands based on the monthly statement
        
        Args:
            daily_register_entry: DailyHologramRegister instance
        """
        try:
            with transaction.atomic():
                # Extract brand and quantity information from monthly statement
                brand_name = daily_register_entry.brand_details
                bottle_size = daily_register_entry.bottle_size
                issued_qty = daily_register_entry.issued_qty
                reference_no = daily_register_entry.reference_no
                
                # Get distillery name from licensee
                distillery_name = daily_register_entry.licensee.manufacturing_unit_name
                
                if not brand_name or not bottle_size or issued_qty <= 0:
                    logger.warning(f"Insufficient data for stock update: {reference_no} - Brand: {brand_name}, Size: {bottle_size}, Qty: {issued_qty}")
                    return False
                
                # Parse bottle size to get capacity in ml
                capacity_ml = BrandWarehouseStockService._parse_bottle_size(bottle_size)
                if not capacity_ml:
                    logger.warning(f"Could not parse bottle size: {bottle_size} for {reference_no}")
                    return False
                
                # Find existing Brand Warehouse entry for this distillery + brand + pack size
                brand_warehouse = BrandWarehouse.objects.filter(
                    distillery_name__icontains=distillery_name,
                    brand_details__icontains=brand_name,
                    capacity_size=capacity_ml
                ).first()
                
                if not brand_warehouse:
                    # Create new entry if not found (this ensures no brands go missing)
                    brand_warehouse = BrandWarehouseStockService._create_brand_warehouse_entry(
                        distillery_name=distillery_name,
                        brand_name=brand_name,
                        capacity_ml=capacity_ml
                    )
                
                if not brand_warehouse:
                    logger.error(f"Could not find/create brand warehouse for {distillery_name} - {brand_name} ({capacity_ml}ml)")
                    return False
                
                # Update current_stock by adding the issued quantity
                previous_stock = brand_warehouse.current_stock
                brand_warehouse.current_stock += issued_qty
                brand_warehouse.save(update_fields=['current_stock', 'updated_at'])
                
                # Update status based on new stock level
                brand_warehouse.update_status()
                
                # Create arrival record for tracking
                BrandWarehouseArrival.objects.create(
                    brand_warehouse=brand_warehouse,
                    reference_no=reference_no,
                    source_type='HOLOGRAM_REGISTER',
                    quantity_added=issued_qty,
                    previous_stock=previous_stock,
                    new_stock=brand_warehouse.current_stock,
                    arrival_date=timezone.now(),
                    notes=f"Monthly Statement: {brand_name} ({bottle_size}) - {daily_register_entry.usage_date}"
                )
                
                logger.info(f"✅ Updated Brand Warehouse stock: {distillery_name} - {brand_name} ({bottle_size})")
                logger.info(f"   Previous stock: {previous_stock}, Added: {issued_qty}, New stock: {brand_warehouse.current_stock}")
                logger.info(f"   Reference: {reference_no}, Status: {brand_warehouse.status}")
                
                return True
                
        except Exception as e:
            logger.error(f"❌ Error updating brand warehouse stock for {reference_no}: {str(e)}")
            return False
    
    @staticmethod
    def check_if_brand_is_new(brand_warehouse, days=7):
        """
        Check if a brand has recent stock updates (within specified days)
        
        Args:
            brand_warehouse: BrandWarehouse instance
            days: Number of days to check for recent updates
            
        Returns:
            bool: True if brand has recent arrivals
        """
        cutoff_date = timezone.now() - timedelta(days=days)
        
        recent_arrivals = brand_warehouse.arrivals.filter(
            arrival_date__gte=cutoff_date
        ).exists()
        
        return recent_arrivals
    
    @staticmethod
    def get_brands_with_new_tags():
        """
        Get all Sikkim brands with "NEW" tags for recent stock updates
        
        Returns:
            dict: Brand warehouse IDs with their "new" status
        """
        try:
            # Get all Sikkim brands
            all_brands = BrandWarehouseStockService.get_all_sikkim_brands_with_stock()
            
            brands_with_tags = {}
            
            for brand in all_brands:
                is_new = BrandWarehouseStockService.check_if_brand_is_new(brand, days=7)
                brands_with_tags[brand.id] = {
                    'is_new': is_new,
                    'last_arrival': brand.arrivals.first().arrival_date if brand.arrivals.exists() else None
                }
            
            return brands_with_tags
            
        except Exception as e:
            logger.error(f"Error getting brands with new tags: {str(e)}")
            return {}
    
    @staticmethod
    def _parse_bottle_size(bottle_size_str):
        """
        Parse bottle size string to extract ml value
        
        Examples: "750ml", "375 ml", "180ML", "750", etc.
        
        Args:
            bottle_size_str: String containing bottle size
            
        Returns:
            int: Capacity in ml or None if parsing fails
        """
        if not bottle_size_str:
            return None
            
        # Remove spaces and convert to lowercase
        size_str = str(bottle_size_str).replace(' ', '').lower()
        
        # Extract numeric part
        import re
        match = re.search(r'(\d+)', size_str)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                pass
        
        return None
    
    @staticmethod
    def _create_brand_warehouse_entry(distillery_name, brand_name, capacity_ml):
        """
        Create new Brand Warehouse entry for Sikkim brands
        
        Args:
            distillery_name: Name of the distillery
            brand_name: Name of the brand
            capacity_ml: Bottle capacity in ml
            
        Returns:
            BrandWarehouse instance or None
        """
        try:
            # Try to find matching LiquorData entry for additional details
            liquor_data = LiquorData.objects.filter(
                manufacturing_unit_name__icontains=distillery_name,
                brand_name__icontains=brand_name,
                pack_size_ml=capacity_ml
            ).first()
            
            # Create new Brand Warehouse entry
            brand_warehouse = BrandWarehouse.objects.create(
                distillery_name=distillery_name,
                brand_type=liquor_data.liquor_type if liquor_data else 'Liquor',
                brand_details=brand_name,
                current_stock=0,  # Will be updated immediately after creation
                capacity_size=capacity_ml,
                liquor_data=liquor_data,
                max_capacity=10000,  # Default max capacity
                reorder_level=1000,  # Default reorder level
                status='OUT_OF_STOCK'  # Will be updated after stock is added
            )
            
            logger.info(f"✅ Created new Brand Warehouse entry: {distillery_name} - {brand_name} ({capacity_ml}ml)")
            return brand_warehouse
            
        except Exception as e:
            logger.error(f"❌ Error creating brand warehouse entry: {str(e)}")
            return None
    
    @staticmethod
    def get_arrival_history(brand_warehouse_id, limit=50):
        """
        Get arrival history for a brand warehouse
        
        Args:
            brand_warehouse_id: ID of the brand warehouse
            limit: Maximum number of records to return
            
        Returns:
            QuerySet of BrandWarehouseArrival records
        """
        return BrandWarehouseArrival.objects.filter(
            brand_warehouse_id=brand_warehouse_id
        ).order_by('-arrival_date')[:limit]
    
    @staticmethod
    def get_arrival_summary(brand_warehouse_id, days=30):
        """
        Get arrival summary for the last N days
        
        Args:
            brand_warehouse_id: ID of the brand warehouse
            days: Number of days to look back
            
        Returns:
            dict: Summary statistics
        """
        from django.db.models import Sum, Count
        from datetime import timedelta
        
        cutoff_date = timezone.now() - timedelta(days=days)
        
        arrivals = BrandWarehouseArrival.objects.filter(
            brand_warehouse_id=brand_warehouse_id,
            arrival_date__gte=cutoff_date
        )
        
        summary = arrivals.aggregate(
            total_arrivals=Count('id'),
            total_quantity=Sum('quantity_added')
        )
        
        return {
            'period_days': days,
            'total_arrivals': summary['total_arrivals'] or 0,
            'total_quantity_added': summary['total_quantity'] or 0,
            'average_per_arrival': (summary['total_quantity'] or 0) / max(summary['total_arrivals'] or 1, 1)
        }
    
    @staticmethod
    def sync_production_with_stock(brand_warehouse_id=None, days=30):
        """
        Sync production batches with brand warehouse stock
        
        This method ensures that the brand warehouse stock reflects all production batches
        and resolves any inconsistencies between production records and stock levels.
        
        Args:
            brand_warehouse_id: Specific brand warehouse to sync (None for all Sikkim brands)
            days: Number of days to look back for production batches
            
        Returns:
            dict: Sync results with counts and details
        """
        from django.apps import apps
        from django.db import transaction
        from datetime import timedelta
        
        try:
            # Get models
            BrandWarehouse = apps.get_model('brand_warehouse', 'BrandWarehouse')
            ProductionBatch = apps.get_model('brand_warehouse', 'ProductionBatch')
            
            # Get date range
            start_date = timezone.now().date() - timedelta(days=days)
            
            # Get brand warehouses to sync - only Sikkim Distilleries Ltd
            if brand_warehouse_id:
                brand_warehouses = BrandWarehouse.objects.filter(id=brand_warehouse_id)
            else:
                brand_warehouses = BrandWarehouse.objects.filter(
                    distillery_name__icontains='Sikkim Distilleries Ltd'
                )
            
            sync_results = {
                'total_processed': 0,
                'total_synced': 0,
                'total_errors': 0,
                'details': []
            }
            
            for brand_warehouse in brand_warehouses:
                try:
                    with transaction.atomic():
                        # Get all production batches for this brand in the date range
                        production_batches = ProductionBatch.objects.filter(
                            brand_warehouse=brand_warehouse,
                            production_date__gte=start_date
                        ).order_by('production_date', 'created_at')
                        
                        # Calculate expected stock from production batches
                        total_production = sum(batch.quantity_produced for batch in production_batches)
                        
                        # Get current stock
                        current_stock = brand_warehouse.current_stock
                        
                        # Check if sync is needed
                        if current_stock != total_production:
                            logger.info(f"🔄 Syncing stock for {brand_warehouse.brand_details}")
                            logger.info(f"   Current: {current_stock}, Expected: {total_production}")
                            
                            # Update stock
                            old_stock = brand_warehouse.current_stock
                            brand_warehouse.current_stock = total_production
                            brand_warehouse.save(update_fields=['current_stock', 'updated_at'])
                            brand_warehouse.update_status()
                            
                            sync_results['total_synced'] += 1
                            sync_results['details'].append({
                                'brand_id': brand_warehouse.id,
                                'brand_name': brand_warehouse.brand_details,
                                'pack_size': brand_warehouse.capacity_size,
                                'old_stock': old_stock,
                                'new_stock': total_production,
                                'production_batches': production_batches.count()
                            })
                            
                            logger.info(f"✅ Stock synced: {old_stock} → {total_production}")
                        
                        sync_results['total_processed'] += 1
                        
                except Exception as e:
                    logger.error(f"❌ Error syncing {brand_warehouse.brand_details}: {str(e)}")
                    sync_results['total_errors'] += 1
            
            logger.info(f"📋 Sync completed: {sync_results['total_synced']} brands synced out of {sync_results['total_processed']} processed")
            return sync_results
            
        except Exception as e:
            logger.error(f"❌ Error in production stock sync: {str(e)}")
            return {
                'total_processed': 0,
                'total_synced': 0,
                'total_errors': 1,
                'error': str(e)
            }