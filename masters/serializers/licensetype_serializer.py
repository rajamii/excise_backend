from rest_framework import serializers
from masters import models as master_models

class LicenseTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = master_models.LicenseType
        fields = '__all__'