from rest_framework import serializers
from .models import License

class LicenseSerializer(serializers.ModelSerializer):
    license_type_name = serializers.CharField(source='license_type.license_type', read_only=True)
    excise_district_name = serializers.CharField(source='excise_district.district', read_only=True)
    application_id = serializers.CharField(source='application.application_id', read_only=True)

    class Meta:
        model = License
        fields = [
            'license_id',
            'application_id',
            'license_type',
            'license_type_name',
            'establishment_name',
            'licensee_name',
            'excise_district',
            'excise_district_name',
            'issue_date',
            'valid_up_to',
            'is_active',
        ]
        read_only_fields = [
            'license_id',
            'application_id',
            'license_type_name',
            'excise_district_name',
            'issue_date',
        ]