from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.contrib import messages
from .models import BrandWarehouse, BrandWarehouseArrival, BrandWarehouseUtilization


@admin.register(BrandWarehouse)
class BrandWarehouseAdmin(admin.ModelAdmin):
    """
    Admin interface for Brand Warehouse with soft delete protection
    """
    list_display = [
        'brand_details', 'distillery_name', 'capacity_size', 
        'current_stock', 'status', 'is_deleted', 'deleted_status'
    ]
    list_filter = [
        'distillery_name', 'brand_type', 'status', 'capacity_size', 'is_deleted'
    ]
    search_fields = ['brand_details', 'distillery_name', 'brand_type']
    readonly_fields = ['created_at', 'updated_at', 'deleted_at', 'deleted_by']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('distillery_name', 'brand_type', 'brand_details')
        }),
        ('Stock Information', {
            'fields': ('current_stock', 'capacity_size', 'status')
        }),
        ('Capacity Settings', {
            'fields': ('max_capacity', 'reorder_level', 'average_daily_usage')
        }),
        ('Soft Delete Information', {
            'fields': ('is_deleted', 'deleted_at', 'deleted_by'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['soft_delete_selected', 'restore_selected']
    
    def get_queryset(self, request):
        """Show all records including soft deleted ones in admin"""
        return BrandWarehouse.objects.all_with_deleted()
    
    def deleted_status(self, obj):
        """Show deletion status with color coding"""
        if obj.is_deleted:
            return format_html(
                '<span style="color: red; font-weight: bold;">DELETED</span><br>'
                '<small>By: {}<br>At: {}</small>',
                obj.deleted_by or 'Unknown',
                obj.deleted_at.strftime('%Y-%m-%d %H:%M') if obj.deleted_at else 'Unknown'
            )
        return format_html('<span style="color: green;">Active</span>')
    deleted_status.short_description = 'Deletion Status'
    
    def soft_delete_selected(self, request, queryset):
        """Soft delete selected brand warehouse entries"""
        active_entries = queryset.filter(is_deleted=False)
        count = active_entries.count()
        
        if count == 0:
            self.message_user(request, "No active entries selected for deletion.", messages.WARNING)
            return
        
        # Perform soft delete
        for entry in active_entries:
            entry.soft_delete(deleted_by=request.user.username)
        
        self.message_user(
            request, 
            f"Successfully soft deleted {count} brand warehouse entries. They can be restored if needed.",
            messages.SUCCESS
        )
    soft_delete_selected.short_description = "Soft delete selected entries"
    
    def restore_selected(self, request, queryset):
        """Restore selected soft deleted brand warehouse entries"""
        deleted_entries = queryset.filter(is_deleted=True)
        count = deleted_entries.count()
        
        if count == 0:
            self.message_user(request, "No deleted entries selected for restoration.", messages.WARNING)
            return
        
        # Perform restoration
        for entry in deleted_entries:
            entry.restore()
        
        self.message_user(
            request, 
            f"Successfully restored {count} brand warehouse entries.",
            messages.SUCCESS
        )
    restore_selected.short_description = "Restore selected deleted entries"
    
    def delete_model(self, request, obj):
        """Override delete to use soft delete"""
        obj.soft_delete(deleted_by=request.user.username)
        messages.success(
            request, 
            f'Brand warehouse "{obj.brand_details}" has been soft deleted. It can be restored if needed.'
        )
    
    def delete_queryset(self, request, queryset):
        """Override bulk delete to use soft delete"""
        active_entries = queryset.filter(is_deleted=False)
        count = active_entries.count()
        
        for entry in active_entries:
            entry.soft_delete(deleted_by=request.user.username)
        
        messages.success(
            request, 
            f'Successfully soft deleted {count} brand warehouse entries. They can be restored if needed.'
        )


@admin.register(BrandWarehouseArrival)
class BrandWarehouseArrivalAdmin(admin.ModelAdmin):
    """
    Admin interface for Brand Warehouse Arrivals
    """
    list_display = [
        'reference_no', 'brand_warehouse', 'source_type', 
        'quantity_added', 'arrival_date'
    ]
    list_filter = ['source_type', 'arrival_date']
    search_fields = ['reference_no', 'brand_warehouse__brand_details']
    readonly_fields = ['created_at']
    
    fieldsets = (
        ('Reference Information', {
            'fields': ('reference_no', 'source_type', 'brand_warehouse')
        }),
        ('Stock Information', {
            'fields': ('quantity_added', 'previous_stock', 'new_stock')
        }),
        ('Timing', {
            'fields': ('arrival_date', 'created_at')
        }),
        ('Additional Details', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
    )


@admin.register(BrandWarehouseUtilization)
class BrandWarehouseUtilizationAdmin(admin.ModelAdmin):
    """
    Admin interface for Brand Warehouse Utilizations
    """
    list_display = [
        'permit_no', 'brand_warehouse', 'distributor', 
        'quantity', 'status', 'date'
    ]
    list_filter = ['status', 'date']
    search_fields = ['permit_no', 'distributor', 'brand_warehouse__brand_details']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Permit Information', {
            'fields': ('permit_no', 'date', 'brand_warehouse')
        }),
        ('Distribution Details', {
            'fields': ('distributor', 'depot_address', 'vehicle')
        }),
        ('Quantity Information', {
            'fields': ('quantity', 'cases', 'bottles_per_case')
        }),
        ('Status and Approval', {
            'fields': ('status', 'approved_by', 'approval_date')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )