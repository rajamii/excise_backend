from rest_framework import serializers
from .models import CompanyDetails, MemberDetails, DocumentDetails

class CompanyDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyDetails
        fields = '__all__'  # Include all fields from the model


class MemberDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = MemberDetails
        fields = '__all__'  # Include all fields from the model


class DocumentDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentDetails
        fields = '__all__'  # Include all fields from the model
