from rest_framework import serializers
from ..models import LicenseFee, LicenseCategory, LicenseSubcategory, Location


class LicenseFeeSerializer(serializers.ModelSerializer):
    """
    Serializer for LicenseFee model with nested representations for read operations.
    """
    # Nested read-only fields for better display
    license_category_name = serializers.CharField(
        source='license_category.license_category', 
        read_only=True
    )
    license_subcategory_name = serializers.CharField(
        source='license_subcategory.description', 
        read_only=True
    )
    location_description = serializers.CharField(
        source='location_code.location_description', 
        read_only=True
    )
    district_name = serializers.CharField(
        source='location_code.district_code.district', 
        read_only=True
    )
    created_by_username = serializers.CharField(
        source='created_by.username', 
        read_only=True
    )

    class Meta:
        model = LicenseFee
        fields = [
            'id',
            'license_category',
            'license_category_name',
            'license_subcategory',
            'license_subcategory_name',
            'location_code',
            'location_description',
            'district_name',
            'license_fee',
            'security_amount',
            'renewal_amount',
            'late_fee',
            'is_active',
            'created_by',
            'created_by_username',
            'operation_date',
        ]
        read_only_fields = ['id', 'operation_date', 'created_by']

    def validate(self, data):
        """
        Validate that the subcategory belongs to the selected category.
        """
        license_category = data.get('license_category')
        license_subcategory = data.get('license_subcategory')

        if license_category and license_subcategory:
            if license_subcategory.category != license_category:
                raise serializers.ValidationError({
                    'license_subcategory': 
                    f'The selected subcategory does not belong to the category "{license_category.license_category}".'
                })

        return data

    def validate_license_fee(self, value):
        """Validate that license fee is positive."""
        if value < 0:
            raise serializers.ValidationError("License fee cannot be negative.")
        return value

    def validate_security_amount(self, value):
        """Validate that security amount is positive."""
        if value < 0:
            raise serializers.ValidationError("Security amount cannot be negative.")
        return value

    def validate_renewal_amount(self, value):
        """Validate that renewal amount is positive."""
        if value < 0:
            raise serializers.ValidationError("Renewal amount cannot be negative.")
        return value

    def validate_late_fee(self, value):
        """Validate that late fee is positive."""
        if value < 0:
            raise serializers.ValidationError("Late fee cannot be negative.")
        return value
