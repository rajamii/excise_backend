from rest_framework import serializers
from models.masters.core.models import PoliceStation

class PoliceStationSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    district = serializers.SerializerMethodField()

    class Meta:
        model = PoliceStation
        fields = [
            'id',
            'police_station',
            'police_station_code',
            'district_code',
            'district',
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

    def get_district(self, obj):
        """Safely get district name, handling NULL district_code"""
        if obj.district_code:
            return obj.district_code.district
        return None
