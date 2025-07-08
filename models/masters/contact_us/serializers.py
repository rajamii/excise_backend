from rest_framework import serializers
from .models import (
    NodalOfficer,
    PublicInformationOfficer,
    DirectorateAndDistrictOfficials,
    GrievanceRedressalOfficer
)

# Serializer for NodalOfficer model
# Used for serializing/deserializing department-level officer info
class NodalOfficerSerializer(serializers.ModelSerializer):
    class Meta:
        model = NodalOfficer
        fields = '__all__'  # Include all model fields


# Serializer for PublicInformationOfficer (inherits from Official)
# Includes additional fields: locationType, location, address
class PublicInformationOfficerSerializer(serializers.ModelSerializer):
    class Meta:
        model = PublicInformationOfficer
        fields = '__all__'  # Include all fields including inherited ones


# Serializer for DirectorateAndDistrictOfficials
# Represents simple name/designation/contact info for officials
class DirectorateAndDistrictOfficialsSerializer(serializers.ModelSerializer):
    class Meta:
        model = DirectorateAndDistrictOfficials
        fields = '__all__'


# Serializer for GrievanceRedressalOfficer (inherits from Official)
# Adds officeLevel and officeSubLevel for department hierarchy
class GrievanceRedressalOfficerSerializer(serializers.ModelSerializer):
    class Meta:
        model = GrievanceRedressalOfficer
        fields = '__all__'
