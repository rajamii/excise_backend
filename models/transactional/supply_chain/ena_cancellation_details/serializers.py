from rest_framework import serializers
from .models import EnaCancellationDetail

class EnaCancellationDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnaCancellationDetail
        fields = '__all__'
