from rest_framework import serializers

from .models import LabelRegistration


class LabelRegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = LabelRegistration
        fields = '__all__'
        read_only_fields = [
            'application_id',
            'applicant',
            'status',
            'created_at',
            'updated_at',
        ]

