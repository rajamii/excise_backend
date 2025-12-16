from rest_framework import serializers
from .models import StatusMaster

class StatusMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = StatusMaster
        fields = '__all__'
