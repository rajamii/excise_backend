from rest_framework import serializers
from masters import models as master_models

class LicenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = master_models.LicenseCategory
        fields = [
            'id',
            'licenseCategoryDescription',
        ]