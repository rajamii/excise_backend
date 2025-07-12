from rest_framework import serializers
from ...core import models as master_models

class LicenseTitleSerializer(serializers.ModelSerializer):
    class Meta:
        model = master_models.LicenseTitle
        fields = [
            'id',
            'description',
        ]