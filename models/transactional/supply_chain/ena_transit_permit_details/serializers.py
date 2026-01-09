from rest_framework import serializers
from .models import EnaTransitPermitDetail

class EnaTransitPermitDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnaTransitPermitDetail
        fields = '__all__'

class TransitPermitProductSerializer(serializers.Serializer):
    """
    Serializer to validate individual product items within the submission payload.
    """
    brand = serializers.CharField(max_length=255)
    size = serializers.CharField() # Input 'size'
    size = serializers.CharField() # Input 'size'
    cases = serializers.IntegerField()
    # New fields
    brand_owner = serializers.CharField(required=False, allow_blank=True)
    liquor_type = serializers.CharField(required=False, allow_blank=True)
    ex_factory_price = serializers.DecimalField(max_digits=15, decimal_places=2, required=False) # Maps to exFactoryPrice
    excise_duty = serializers.DecimalField(max_digits=15, decimal_places=2, required=False) # Maps to exciseDuty
    education_cess = serializers.DecimalField(max_digits=15, decimal_places=2, required=False) # Maps to educationCess
    additional_excise = serializers.DecimalField(max_digits=15, decimal_places=2, required=False) # Maps to additionalExcise
    manufacturing_unit_name = serializers.CharField(required=False, allow_blank=True) # New field


class TransitPermitSubmissionSerializer(serializers.Serializer):
    """
    Serializer to validate the full submission payload.
    CamelCaseJSONParser will convert incoming camelCase keys to snake_case.
    """
    bill_no = serializers.CharField()
    sole_distributor = serializers.CharField() # maps from soleDistributor
    date = serializers.DateField()
    depot_address = serializers.CharField()
    vehicle_number = serializers.CharField()
    products = TransitPermitProductSerializer(many=True)

    def validate(self, attrs):
        return attrs
