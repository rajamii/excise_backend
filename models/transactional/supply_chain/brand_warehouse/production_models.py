from django.db import models
from django.utils import timezone


class ProductionBatch(models.Model):
    """
    Model to track daily production batches for brands
    """
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]

    # Foreign Key to Brand Warehouse
    brand_warehouse = models.ForeignKey(
        'brand_warehouse.BrandWarehouse',
        on_delete=models.CASCADE,
        related_name='production_batches',
        db_column='brand_warehouse_id',
        help_text='Related brand warehouse entry'
    )

    # Production Information
    batch_reference = models.CharField(
        max_length=100,
        unique=True,
        db_column='batch_reference',
        help_text='Production batch reference number (e.g., PROD-2024-001)'
    )
    production_date = models.DateField(
        default=timezone.now,
        db_column='production_date',
        help_text='Date of production'
    )
    production_time = models.TimeField(
        default=timezone.now,
        db_column='production_time',
        help_text='Time of production'
    )

    # Quantity Information
    quantity_produced = models.IntegerField(
        db_column='quantity_produced',
        help_text='Quantity produced in this batch (in units/bottles)'
    )
    stock_before = models.IntegerField(
        db_column='stock_before',
        help_text='Stock level before this production'
    )
    stock_after = models.IntegerField(
        db_column='stock_after',
        help_text='Stock level after this production'
    )

    # Officer Information
    production_manager = models.CharField(
        max_length=255,
        db_column='production_manager',
        help_text='Name of the production manager/officer'
    )
    approved_by = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_column='approved_by',
        help_text='Name of the approving officer'
    )

    # Status and Notes
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='COMPLETED',
        db_column='status',
        help_text='Status of the production batch'
    )
    notes = models.TextField(
        blank=True,
        null=True,
        db_column='notes',
        help_text='Additional notes about the production batch'
    )

    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_column='created_at'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        db_column='updated_at'
    )

    class Meta:
        db_table = 'production_batch'
        ordering = ['-production_date', '-production_time']
        verbose_name = 'Production Batch'
        verbose_name_plural = 'Production Batches'
        indexes = [
            models.Index(fields=['brand_warehouse', 'production_date']),
            models.Index(fields=['batch_reference']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.batch_reference} - {self.brand_warehouse.brand_details} ({self.quantity_produced} units)"

    def save(self, *args, **kwargs):
        """Override save to update brand warehouse stock"""
        from django.apps import apps
        from django.db import transaction
        import logging
        
        logger = logging.getLogger(__name__)
        is_new = self.pk is None
        
        if is_new:
            # Use transaction to ensure atomicity
            with transaction.atomic():
                # For new production batches, update the brand warehouse stock
                self.stock_before = self.brand_warehouse.current_stock
                self.stock_after = self.stock_before + self.quantity_produced
                
                logger.info(f"🏭 Production Batch: Updating stock for {self.brand_warehouse.brand_details}")
                logger.info(f"   Previous stock: {self.stock_before}")
                logger.info(f"   Production quantity: {self.quantity_produced}")
                logger.info(f"   New stock: {self.stock_after}")
                
                # Update brand warehouse stock
                self.brand_warehouse.current_stock = self.stock_after
                self.brand_warehouse.save(update_fields=['current_stock', 'updated_at'])
                
                # Update status based on new stock level
                self.brand_warehouse.update_status()
                
                logger.info(f"✅ Brand warehouse stock updated successfully: {self.brand_warehouse.current_stock} units")
        
        super().save(*args, **kwargs)

    @property
    def formatted_reference(self):
        """Get formatted reference for display"""
        return self.batch_reference

    @property
    def production_datetime(self):
        """Get combined production datetime"""
        return timezone.datetime.combine(self.production_date, self.production_time)