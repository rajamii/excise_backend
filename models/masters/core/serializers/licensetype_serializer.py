from rest_framework import serializers
from models.masters.core import models as master_models

class LicenseTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = master_models.LicenseType
        fields = [
            'id',
            'licenseType',
        ]
