from rest_framework import serializers
from models.masters.core import models as master_models

class LicenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = master_models.LicenseCategory
        fields = ['id', 'license_category', 'old_license_cat_code', 'is_active', 'is_special_permit_allowed', 'is_distributor_user']

    def to_internal_value(self, data):
        if isinstance(data, dict):
            data = data.copy()
            if 'licenseCategory' in data and 'license_category' not in data:
                data['license_category'] = data.pop('licenseCategory')
            if 'isSpecialPermitAllowed' in data and 'is_special_permit_allowed' not in data:
                data['is_special_permit_allowed'] = data.pop('isSpecialPermitAllowed')
            if 'isDistributorUser' in data and 'is_distributor_user' not in data:
                data['is_distributor_user'] = data.pop('isDistributorUser')
            if 'oldLicenseCatCode' in data and 'old_license_cat_code' not in data:
                data['old_license_cat_code'] = data.pop('oldLicenseCatCode')
            if 'isActive' in data and 'is_active' not in data:
                data['is_active'] = data.pop('isActive')
        return super().to_internal_value(data)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['licenseCategory'] = instance.license_category
        representation['isSpecialPermitAllowed'] = instance.is_special_permit_allowed
        representation['isDistributorUser'] = instance.is_distributor_user
        representation['isActive'] = instance.is_active
        return representation

