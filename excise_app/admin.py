# bookapp/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from excise_app.models import CustomUser,District, Subdivision

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ('username',  'role', 'phonenumber', 'is_active', 'is_staff')  # Updated 'police_id' to 'user_id'
    search_fields = ('username', 'user_id')  # Updated 'police_id' to 'user_id'
    ordering = ('username',)
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ( 'role', 'phonenumber', 'district', 'subdivision', 'address')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'user_permissions', 'groups')}),
        ('Important Dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username',  'role', 'phonenumber', 'password1', 'password2'),
        }),
    )
    filter_horizontal = ('user_permissions', 'groups')

@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ('District', 'DistrictCode', 'IsActive', 'StateCode')
    search_fields = ('District', 'DistrictCode')
    list_filter = ('IsActive', 'StateCode')  # Filter by active status and state
    ordering = ('DistrictCode',)

@admin.register(Subdivision)
class SubdivisionAdmin(admin.ModelAdmin):
    list_display = ('SubDivisionName', 'SubDivisionCode', 'IsActive', 'DistrictCode')
    search_fields = ('SubDivisionName', 'SubDivisionCode')
    list_filter = ('IsActive', 'DistrictCode')  # Filter by active status and district
    ordering = ('SubDivisionCode',)