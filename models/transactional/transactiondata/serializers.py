from rest_framework import serializers
from .models import TransactionData
from auth.user.models import CustomUser
from models.masters.core.models import District, Subdivision, LicenseCategory

class TransactionDataSerializer(serializers.ModelSerializer):
    # This field expects the primary key (ID) of the CustomUser.
    licensee_id = serializers.PrimaryKeyRelatedField(queryset=CustomUser.objects.all())

    # Use SlugRelatedField to map 'district_code' from input to a District object.
    # 'slug_field' tells DRF to use 'district_code' on the District model for lookup.
    district = serializers.SlugRelatedField(queryset=District.objects.all(), slug_field='district_code')

    # Use SlugRelatedField to map 'subdivision_code' from input to a Subdivision object.
    # 'slug_field' tells DRF to use 'subdivision_code' on the Subdivision model for lookup.
    subdivision = serializers.SlugRelatedField(queryset=Subdivision.objects.all(), slug_field='subdivision_code')

    # This field expects the primary key (ID) of the LicenseCategory.
    # 'allow_null=True' is crucial because your model allows null for this field.
    license_category = serializers.PrimaryKeyRelatedField(queryset=LicenseCategory.objects.all(), allow_null=True)

    # updated_by should be optional for creation and automatically set by the view.
    # For updates, if provided, it should be the CustomUser's ID.
    # 'required=False' and 'allow_null=True' match your model definition.
    updated_by = serializers.PrimaryKeyRelatedField(queryset=CustomUser.objects.all(), required=False, allow_null=True)

    class Meta:
        model = TransactionData
        fields = [
            'licensee_id',
            'district',
            'subdivision',
            'license_category',
            'longitude',
            'latitude',
            'created_at',
            'updated_by'
        ]
        # 'created_at' is auto_now_add=True in the model, so it must be read-only.
        read_only_fields = ['created_at']

    def validate(self, data):
        # After serializer.is_valid(), data.get() for SlugRelatedFields
        # will return the actual model instance (District, Subdivision), not just the code.
        licensee_id_obj = data.get('licensee_id')
        district_obj = data.get('district')
        subdivision_obj = data.get('subdivision')

        # Ensure that the objects exist before trying to access their attributes
        if not licensee_id_obj:
            raise serializers.ValidationError("Licensee ID is required.")
        if not district_obj:
            raise serializers.ValidationError("District is required.")
        if not subdivision_obj:
            raise serializers.ValidationError("Subdivision is required.")

        # Validate user's district and subdivision using the objects
        if not CustomUser.objects.filter(
            id=licensee_id_obj.id,
            district=district_obj.district_code, # Access the code from the resolved object
            subdivision=subdivision_obj.subdivision_code # Access the code from the resolved object
        ).exists():
            raise serializers.ValidationError(
                "District or subdivision does not match the user's registered data."
            )

        # Validate subdivision belongs to district
        # Compare the district object of the subdivision with the district object provided
        if subdivision_obj.district_code != district_obj:
            raise serializers.ValidationError(
                "Subdivision does not belong to the specified district."
            )

        # Validate longitude and latitude ranges
        longitude = data.get('longitude')
        latitude = data.get('latitude')

        if not (-180 <= longitude <= 180):
            raise serializers.ValidationError("Longitude must be between -180 and 180.")
        if not (-90 <= latitude <= 90):
            raise serializers.ValidationError("Latitude must be between -90 and 90.")

        return data

    def to_representation(self, instance):
        representation = super().to_representation(instance)

        # Customize representation for related fields to show more meaningful data
        if instance.district:
            representation['district'] = {
                'district_code': instance.district.district_code,
                'district_name': instance.district.district
            }
        else:
            representation['district'] = None

        if instance.subdivision:
            representation['subdivision'] = {
                'subdivision_code': instance.subdivision.subdivision_code,
                'subdivision_name': instance.subdivision.subdivision
            }
        else:
            representation['subdivision'] = None

        if instance.license_category:
            representation['license_category'] = {
                'id': instance.license_category.id,
                'name': instance.license_category.license_category
            }
        else:
            representation['license_category'] = None
        
        # Ensure updated_by shows username, or None if not set
        representation['updated_by'] = (
            instance.updated_by.username if instance.updated_by else None
        )
        return representation