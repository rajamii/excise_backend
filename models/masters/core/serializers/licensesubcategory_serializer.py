from rest_framework import serializers
from models.masters.core import models as master_models

class LicenseSubcategorySerializer(serializers.ModelSerializer):
    category = serializers.PrimaryKeyRelatedField(
        queryset=master_models.LicenseCategory.objects.all(),
        required=False  # Allow PATCH without sending category
    )

    class Meta:
        model = master_models.LicenseSubcategory
        fields = ['id', 'description', 'old_license_cat_code', 'old_license_scat_code', 'category', 'dry_day_fee_type', 'is_active']

    def to_internal_value(self, data):
        if isinstance(data, dict):
            data = data.copy()
            if 'dryDayFeeType' in data and 'dry_day_fee_type' not in data:
                data['dry_day_fee_type'] = data.pop('dryDayFeeType')
            if 'isActive' in data and 'is_active' not in data:
                data['is_active'] = data.pop('isActive')
        return super().to_internal_value(data)

    def update(self, instance, validated_data):
        """Override update to use update_fields so model validators only run on changed fields."""
        update_fields = []
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
            update_fields.append(attr)
        if update_fields:
            instance.save(update_fields=update_fields)
        return instance

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['category'] = {
            'id': instance.category.id,
            'licenseCategory': instance.category.license_category
        }
        return representation
