from rest_framework import serializers
from .models import SupplyChainUserProfile

class SupplyChainUserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplyChainUserProfile
        fields = '__all__'
        read_only_fields = ('user', 'created_at', 'updated_at')
