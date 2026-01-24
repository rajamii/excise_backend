from django.db import models


class BrandWarehouse(models.Model):
    """
    Model to store brand warehouse information including stock levels and capacity
    """
    STATUS_CHOICES = [
        ('IN_STOCK', 'In Stock'),
        ('LOW_STOCK', 'Low Stock'),
        ('OUT_OF_STOCK', 'Out of Stock'),
        ('OVERSTOCKED', 'Overstocked'),
    ]

    # Basic Information
    distillery_name = models.CharField(
        max_length=255,
        db_column='distillery_name',
        help_text='Name of the distillery/manufacturing unit'
    )
    brand_type = models.CharField(
        max_length=100,
        db_column='brand_type',
        help_text='Type of brand (e.g., Whisky, Rum, Vodka)'
    )
    brand_details = models.TextField(
        db_column='brand_details',
        blank=True,
        null=True,
        help_text='Detailed information about the brand'
    )

    # Stock Information
    current_stock = models.IntegerField(
        default=0,
        db_column='current_stock',
        help_text='Current stock quantity in units'
    )

    # Capacity Information (in ml)
    capacity_size = models.IntegerField(
        default=0,
        db_column='capacity_size',
        help_text='Pack size in ml (e.g., 750, 375, 180)'
    )

    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='IN_STOCK',
        db_column='status',
        help_text='Current stock status'
    )

    # Link to Liquor Data (for Sikkim brands)
    liquor_data = models.ForeignKey(
        'liquor_data.LiquorData',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='warehouse_entries',
        db_column='liquor_data_id',
        help_text='Link to liquor data details (for Sikkim brands)'
    )

    # Additional fields
    reorder_level = models.IntegerField(
        default=0,
        db_column='reorder_level',
        help_text='Minimum stock level before reordering'
    )
    max_capacity = models.IntegerField(
        default=0,
        db_column='max_capacity',
        help_text='Maximum storage capacity'
    )
    average_daily_usage = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        db_column='average_daily_usage',
        help_text='Average daily usage in units'
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
        db_table = 'brand_warehouse'
        ordering = ['-updated_at']
        verbose_name = 'Brand Warehouse'
        verbose_name_plural = 'Brand Warehouses'
        indexes = [
            models.Index(fields=['distillery_name']),
            models.Index(fields=['brand_type']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.distillery_name} - {self.brand_type}"

    @property
    def total_capacity(self):
        """Total capacity for this specific pack size"""
        return self.max_capacity

    @property
    def total_utilized(self):
        """Calculate total quantity utilized from all utilization records"""
        return self.utilizations.filter(
            status__in=['APPROVED', 'IN_TRANSIT', 'DELIVERED']
        ).aggregate(
            total=models.Sum('quantity')
        )['total'] or 0

    @property
    def utilization_percentage(self):
        """Calculate utilization percentage"""
        if self.total_capacity == 0:
            return 0
        return (self.current_stock / self.total_capacity) * 100

    def update_status(self):
        """Update stock status based on current stock levels"""
        if self.current_stock == 0:
            self.status = 'OUT_OF_STOCK'
        elif self.current_stock <= self.reorder_level:
            self.status = 'LOW_STOCK'
        elif self.current_stock > self.max_capacity:
            self.status = 'OVERSTOCKED'
        else:
            self.status = 'IN_STOCK'
        self.save(update_fields=['status', 'updated_at'])


class BrandWarehouseUtilization(models.Model):
    """
    Model to track utilization of brand warehouse stock through transit permits
    """
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('IN_TRANSIT', 'In Transit'),
        ('DELIVERED', 'Delivered'),
        ('CANCELLED', 'Cancelled'),
    ]

    # Foreign Key to Brand Warehouse
    brand_warehouse = models.ForeignKey(
        BrandWarehouse,
        on_delete=models.CASCADE,
        related_name='utilizations',
        db_column='brand_warehouse_id',
        help_text='Related brand warehouse entry'
    )

    # Transit Permit Information
    permit_no = models.CharField(
        max_length=100,
        db_column='permit_no',
        help_text='Transit permit number'
    )
    date = models.DateField(
        db_column='date',
        help_text='Date of transit permit'
    )
    distributor = models.CharField(
        max_length=255,
        db_column='distributor',
        help_text='Distributor name'
    )
    depot_address = models.TextField(
        db_column='depot_address',
        help_text='Depot/destination address'
    )
    vehicle = models.CharField(
        max_length=50,
        db_column='vehicle',
        help_text='Vehicle number'
    )
    quantity = models.IntegerField(
        db_column='quantity',
        help_text='Quantity utilized/dispatched'
    )
    
    # Additional Details
    cases = models.IntegerField(
        default=0,
        db_column='cases',
        help_text='Number of cases'
    )
    bottles_per_case = models.IntegerField(
        default=12,
        db_column='bottles_per_case',
        help_text='Number of bottles per case'
    )

    # Status and Approval
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PENDING',
        db_column='status',
        help_text='Status of the transit permit'
    )
    approved_by = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_column='approved_by',
        help_text='Name of the approving officer'
    )
    approval_date = models.DateTimeField(
        blank=True,
        null=True,
        db_column='approval_date',
        help_text='Date and time of approval'
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
        db_table = 'brand_warehouse_utilization'
        ordering = ['-date', '-created_at']
        verbose_name = 'Brand Warehouse Utilization'
        verbose_name_plural = 'Brand Warehouse Utilizations'
        indexes = [
            models.Index(fields=['permit_no']),
            models.Index(fields=['date']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.permit_no} - {self.brand_warehouse.distillery_name} ({self.quantity} units)"

    @property
    def total_bottles(self):
        """Calculate total bottles from cases and bottles per case"""
        return self.cases * self.bottles_per_case

    def save(self, *args, **kwargs):
        """Override save to update brand warehouse stock on utilization"""
        is_new = self.pk is None
        old_quantity = 0
        
        if not is_new:
            old_instance = BrandWarehouseUtilization.objects.get(pk=self.pk)
            old_quantity = old_instance.quantity if old_instance.status in ['APPROVED', 'IN_TRANSIT', 'DELIVERED'] else 0
        
        super().save(*args, **kwargs)
        
        # Update brand warehouse stock
        if self.status in ['APPROVED', 'IN_TRANSIT', 'DELIVERED']:
            new_quantity = self.quantity
            stock_change = new_quantity - old_quantity
            
            if stock_change != 0:
                self.brand_warehouse.current_stock = max(0, self.brand_warehouse.current_stock - stock_change)
                self.brand_warehouse.update_status()
