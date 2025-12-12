from rest_framework import serializers
from .models import EnaCancellationDetail

class EnaCancellationDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnaCancellationDetail
        fields = '__all__'

class CancellationCreateSerializer(serializers.Serializer):
    referenceNo = serializers.CharField(max_length=100)
    permitNumbers = serializers.ListField(child=serializers.CharField(max_length=100))
    licenseeId = serializers.CharField(max_length=50)

