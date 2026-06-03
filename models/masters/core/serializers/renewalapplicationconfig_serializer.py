from rest_framework import serializers
from models.masters.core.models import RenewalApplicationConfig

class RenewalApplicationConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = RenewalApplicationConfig
        fields = ['id', 'renewal_month', 'renewal_day', 'renewal_time']
