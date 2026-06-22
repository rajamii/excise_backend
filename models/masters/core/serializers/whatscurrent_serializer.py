from rest_framework import serializers
from models.masters.core import models as master_models

class WhatsCurrentSerializer(serializers.ModelSerializer):
    class Meta:
        model = master_models.WhatsCurrent
        fields = '__all__'
