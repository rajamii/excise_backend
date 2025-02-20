from rest_framework import serializers
from masters import models as master_models



class DistrictSerializer(serializers.ModelSerializer):
    stateName = serializers.CharField(source='StateCode.State', read_only=True)

    class Meta: 
        model = master_models.District
        fields = '__all__'  # Corrected from '_all_'

class SubDivisonSerializer(serializers.ModelSerializer):
    District = serializers.CharField(source='DistrictCode.District', read_only=True)

    class Meta: 
        model = master_models.Subdivision
        fields = '__all__'  # Corrected from '_all_'

class PoliceStationSerializer(serializers.ModelSerializer):
    SubDivisionName = serializers.CharField(source='SubDivisionCode.SubDivisionName', read_only=True)
    District = serializers.CharField(source='SubDivisionCode.DistrictCode.District', read_only=True)

    class Meta: 
        model = master_models.PoliceStation
        fields = '__all__'  # Corrected from '_all_'
