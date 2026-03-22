from django.contrib import admin
from .models import BrandOwner, BrandOwnerFee, BrandOwnerType, LiquorBrand, LiquorCategory, LiquorKind, LiquorType


@admin.register(BrandOwnerType)
class BrandOwnerTypeAdmin(admin.ModelAdmin):
    list_display = ['brand_owner_type_code', 'brand_owner_type_desc']


@admin.register(BrandOwner)
class BrandOwnerAdmin(admin.ModelAdmin):
    list_display = ['brand_owner_code', 'brand_owner_name', 'brand_owner_type', 'enable_status']
    list_filter = ['brand_owner_type', 'enable_status']
    search_fields = ['brand_owner_code', 'brand_owner_name', 'brand_owner_pan']


@admin.register(LiquorCategory)
class LiquorCategoryAdmin(admin.ModelAdmin):
    list_display = ['liquor_cat_code', 'liquor_cat_abbr', 'liquor_cat_desc', 'delete_status']


@admin.register(LiquorKind)
class LiquorKindAdmin(admin.ModelAdmin):
    list_display = ['liquor_cat', 'liquor_kind_code', 'liquor_kind_abbr', 'liquor_kind_desc', 'delete_status']
    list_filter = ['liquor_cat']


@admin.register(LiquorType)
class LiquorTypeAdmin(admin.ModelAdmin):
    list_display = ['liquor_cat', 'liquor_kind', 'liquor_type_code', 'liquor_type_desc', 'delete_status']
    list_filter = ['liquor_cat', 'liquor_kind']


@admin.register(LiquorBrand)
class LiquorBrandAdmin(admin.ModelAdmin):
    list_display = ['liquor_brand_code', 'liquor_brand_desc', 'liquor_cat', 'liquor_type', 'delete_status']
    list_filter = ['liquor_cat', 'liquor_kind', 'liquor_type', 'delete_status']
    search_fields = ['liquor_brand_code', 'liquor_brand_desc']


@admin.register(BrandOwnerFee)
class BrandOwnerFeeAdmin(admin.ModelAdmin):
    list_display = ['id', 'registration_fee', 'collaboration_fees', 'security_deposit', 'active_status', 'from_date']
    list_filter = ['active_status']
