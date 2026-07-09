from rest_framework import serializers
from models.masters.core import models as master_models

class LicenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = master_models.LicenseCategory
        fields = ['id', 'license_category', 'old_license_cat_code', 'is_active']
