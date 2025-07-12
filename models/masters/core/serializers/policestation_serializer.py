from rest_framework import serializers
from models.masters.core.models import PoliceStation
from .subdivision_serializer import SubdivisionSerializer  # Optional, for nesting

class PoliceStationSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    subdivision = serializers.CharField(
        source='subdivision_code.subdivision', 
        read_only=True
    )

    class Meta:
        model = PoliceStation
        fields = [
            'id',
            'police_station',
            'police_station_code',
            'subdivision_code',
            'subdivision',
            'is_active',
            'status'
        ]
        extra_kwargs = {
            'police_station_code': {
                'validators': []  # Handled manually in validate
            }
        }

    def validate_police_station_code(self, value):
        """Ensure police station code is unique"""
        queryset = PoliceStation.objects.filter(police_station_code=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("Police station code must be unique")
        return value

    def get_status(self, obj):
        return "Active" if obj.is_active else "Inactive"
