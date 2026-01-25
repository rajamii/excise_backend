from django.db.models.signals import post_save
from django.dispatch import receiver
from models.transactional.supply_chain.hologram.models import DailyHologramRegister
from .services import BrandWarehouseStockService
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=DailyHologramRegister)
def update_brand_warehouse_stock_on_save(sender, instance, created, **kwargs):
    """
    Signal handler to update Brand Warehouse current_stock when Daily Hologram Register is saved
    
    This triggers when:
    1. Daily Hologram Register entry is marked as fixed (is_fixed=True)
    2. Entry has issued quantity > 0 (actual production happened)
    3. Entry belongs to Sikkim Distillery (manufacturing unit)
    4. Stock has not been updated yet (stock_updated=False)
    
    NOTE: This signal is designed to work alongside ProductionBatch entries.
    If a ProductionBatch already exists for the same production, we skip the stock update
    to avoid double-counting.
    """
    try:
        # Only process if entry is fixed (saved/locked) and has production
        if not instance.is_fixed or instance.issued_qty <= 0:
            return
        
        # CRITICAL: Check if stock has already been updated for this entry
        if instance.stock_updated:
            logger.info(f"⚠️ Skipping stock update for {instance.reference_no} - stock already updated")
            return
        
        # Check if this is for Sikkim Distilleries Ltd (not other Sikkim-based companies)
        distillery_name = instance.licensee.manufacturing_unit_name if instance.licensee else ""
        if not distillery_name or "Sikkim Distilleries Ltd" not in distillery_name:
            logger.info(f"Skipping non-Sikkim Distilleries Ltd company: {distillery_name}")
            return
        
        # Check if there's already a ProductionBatch for this production
        # to avoid double-counting stock updates
        from django.apps import apps
        ProductionBatch = apps.get_model('brand_warehouse', 'ProductionBatch')
        
        # Look for production batches on the same date with similar quantity
        existing_production = ProductionBatch.objects.filter(
            production_date=instance.usage_date,
            quantity_produced=instance.issued_qty,
            brand_warehouse__brand_details__icontains=instance.brand_details,
            brand_warehouse__capacity_size=BrandWarehouseStockService._parse_bottle_size(instance.bottle_size)
        ).exists()
        
        if existing_production:
            logger.info(f"⚠️ Skipping stock update for {instance.reference_no} - ProductionBatch already exists")
            logger.info(f"   This prevents double-counting of production stock")
            return
        
        # Check for duplicate entries with same reference number and brand
        duplicate_entries = DailyHologramRegister.objects.filter(
            reference_no=instance.reference_no,
            brand_details=instance.brand_details,
            bottle_size=instance.bottle_size,
            issued_qty=instance.issued_qty,
            stock_updated=True
        ).exclude(id=instance.id)
        
        if duplicate_entries.exists():
            logger.info(f"⚠️ Skipping stock update for {instance.reference_no} - duplicate entry already processed")
            logger.info(f"   Found {duplicate_entries.count()} duplicate entries with stock already updated")
            return
        
        logger.info(f"🔄 Processing Brand Warehouse stock update for Monthly Statement: {instance.reference_no}")
        logger.info(f"   Distillery: {distillery_name}")
        logger.info(f"   Brand: {instance.brand_details}")
        logger.info(f"   Size: {instance.bottle_size}")
        logger.info(f"   Issued Qty: {instance.issued_qty}")
        logger.info(f"   Usage Date: {instance.usage_date}")
        
        # Update brand warehouse stock
        success = BrandWarehouseStockService.update_stock_from_hologram_register(instance)
        
        if success:
            # Mark this entry as having its stock updated
            DailyHologramRegister.objects.filter(id=instance.id).update(stock_updated=True)
            logger.info(f"✅ Successfully updated Brand Warehouse stock for {instance.reference_no}")
            logger.info(f"   Entry marked as stock_updated=True to prevent duplicate updates")
        else:
            logger.warning(f"⚠️ Failed to update Brand Warehouse stock for {instance.reference_no}")
            
    except Exception as e:
        logger.error(f"❌ Error in Brand Warehouse stock update signal for {instance.reference_no}: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())


@receiver(post_save, sender=DailyHologramRegister)
def log_monthly_statement_changes(sender, instance, created, **kwargs):
    """
    Signal handler to log Monthly Statement changes for audit purposes
    """
    try:
        if created:
            logger.info(f"📝 New Monthly Statement created: {instance.reference_no} - {instance.licensee.manufacturing_unit_name if instance.licensee else 'Unknown'}")
        elif instance.is_fixed:
            logger.info(f"🔒 Monthly Statement fixed: {instance.reference_no}")
            logger.info(f"   Brand: {instance.brand_details} ({instance.bottle_size})")
            logger.info(f"   Production: {instance.issued_qty} units")
            logger.info(f"   Wastage: {instance.wastage_qty} units")
            logger.info(f"   Date: {instance.usage_date}")
            
    except Exception as e:
        logger.error(f"❌ Error in monthly statement logging signal: {str(e)}")