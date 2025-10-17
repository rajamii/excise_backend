from rest_framework import serializers
from .models import EnaRequisitionDetail


class EnaRequisitionDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnaRequisitionDetail
        fields = '__all__'


