from rest_framework import serializers
from models.masters.core.models import PoliceStation
from .subdivision_serializer import SubdivisionSerializer  # For nested if needed

class PoliceStationSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    subdivision_name = serializers.CharField(
        source='SubDivisionCode.SubDivisionName', 
        read_only=True
    )
    
    class Meta:
        model = PoliceStation
        fields = [
            'id',
            'PoliceStationName',
            'PoliceStationCode',
            'SubDivisionCode',
            'subdivision_name',
            'IsActive',
            'status'
        ]
        extra_kwargs = {
            'PoliceStationCode': {
                'validators': []  # Handled in validate
            }
        }

    def validate_PoliceStationCode(self, value):
        """Ensure police station code is unique"""
        queryset = PoliceStation.objects.filter(PoliceStationCode=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("Police station code must be unique")
        return value

    def get_status(self, obj):
        return "Active" if obj.IsActive else "Inactive"
