from rest_framework import serializers
from .models import PreventiveRaid, PreventiveRaidImage


class PreventiveRaidImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PreventiveRaidImage
        fields = ['id', 'image']


class PreventiveRaidSerializer(serializers.ModelSerializer):
    images = PreventiveRaidImageSerializer(many=True, read_only=True)

    class Meta:
        model = PreventiveRaid
        fields = ['id', 'title', 'subject', 'date', 'images', 'created_at', 'updated_at']
