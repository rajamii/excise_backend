from rest_framework import serializers
from .models import NodalOfficer, PublicInformationOfficer, DirectorateAndDistrictOfficials, GrievanceRedressalOfficer

class NodalOfficerSerializer(serializers.ModelSerializer):
    class Meta:
        model = NodalOfficer
        fields = '__all__'

class PublicInformationOfficerSerializer(serializers.ModelSerializer):
    class Meta:
        model = PublicInformationOfficer
        fields = '__all__'

class DirectorateAndDistrictOfficialsSerializer(serializers.ModelSerializer):
    class Meta:
        model = DirectorateAndDistrictOfficials
        fields = '__all__'

class GrievanceRedressalOfficerSerializer(serializers.ModelSerializer):
    class Meta:
        model = GrievanceRedressalOfficer
        fields = '__all__'
