from rest_framework import serializers
from models.masters.core import models as master_models

class LicenseSubcategorySerializer(serializers.ModelSerializer):
    category = serializers.PrimaryKeyRelatedField(queryset=master_models.LicenseCategory.objects.all())

    class Meta:
        model = master_models.LicenseSubcategory
        fields = ['id', 'description', 'category']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['category'] = {
            'id': instance.category.id,
            'licenseCategory': instance.category.license_category
        }
        return representation