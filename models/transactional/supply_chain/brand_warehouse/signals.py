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
        
        # Check if an arrival has already been recorded specifically for this register entry
        from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouseArrival
        entry_tag = f"[register_id:{instance.id}]"
        if BrandWarehouseArrival.objects.filter(reference_no=instance.reference_no, notes__contains=entry_tag).exists():
            logger.info(f"⚠️ Stock already recorded in arrival for entry #{instance.id} ({instance.reference_no})")
            DailyHologramRegister.objects.filter(id=instance.id).update(stock_updated=True)
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
