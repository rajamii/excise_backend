from rest_framework import serializers
from models.masters.core.models import District
from .state_serializer import StateSerializer  # Import if you need nested state

class DistrictSerializer(serializers.ModelSerializer):
    # Computed fields
    status = serializers.SerializerMethodField()
    state_name = serializers.CharField(source='StateCode.State', read_only=True)
    
    # If you want nested subdivisions
    # subdivisions = SubdivisionSerializer(many=True, read_only=True)
    
    class Meta:
        model = District
        fields = [
            'id',
            'District',
            'DistrictNameLL',
            'DistrictCode',
            'StateCode',
            'state_name',
            'IsActive',
            'status',
            # 'subdivisions'  # Uncomment if using nested
        ]
        extra_kwargs = {
            'DistrictCode': {
                'validators': []  # We'll handle in validate
            },
            'StateCode': {'read_only': False}  # Allow setting via ID
        }

    def validate_DistrictCode(self, value):
        """Ensure district code is unique per state"""
        queryset = District.objects.filter(DistrictCode=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("District code must be unique")
        return value

    def validate(self, attrs):
        """Cross-field validation"""
        if 'District' in attrs and 'DistrictNameLL' in attrs:
            if attrs['District'].lower() == attrs['DistrictNameLL'].lower():
                raise serializers.ValidationError(
                    "Name and local name cannot be identical"
                )
        return attrs

    def get_status(self, obj):
        return "Active" if obj.IsActive else "Inactive"
