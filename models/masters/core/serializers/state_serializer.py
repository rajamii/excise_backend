 # serializers/state_serializer.py
from rest_framework import serializers
from django.core.validators import MinValueValidator, MaxValueValidator
from rest_framework.exceptions import PermissionDenied
from models.masters.core.models import State
from django.utils import timezone

class StateSerializer(serializers.ModelSerializer):
    # ===== 1. DECLARED FIELDS (Custom behavior) =====
    status = serializers.SerializerMethodField(read_only=True)
    state_code = serializers.IntegerField(
        validators=[
            MinValueValidator(1000, message="State code must be ≥1000"),
            MaxValueValidator(9999, message="State code must be ≤9999")
        ]
    )

    # ===== 2. META CONFIGURATION =====
    class Meta:
        model = State
        fields = [
            'id',
            'state', 
            'state_code',
            'is_active',
            'status'  # Computed field
        ]
        extra_kwargs = {
            'state_code': {
                'validators': []  # Let validate_state_code handle it
            }
        }

    # ===== 3. FIELD VALIDATORS =====
    def validate_StateCode(self, value: int) -> int:
        """Ensure state code is unique (excluding current instance)"""
        queryset = State.objects.filter(state_code=value)
        
        # During updates, exclude current instance
        if self.instance and self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
            
        if queryset.exists():
            raise serializers.ValidationError("This state code is already in use")
        return value

    # ===== 4. OBJECT VALIDATION =====
    def validate(self, attrs: dict) -> dict:
        """Cross-field validation"""
        # Auto-set modified timestamp
        attrs['last_modified'] = timezone.now()
        return attrs

    # ===== 5. COMPUTED FIELDS =====
    def get_status(self, obj) -> str:
        """Dynamic status field"""
        return "Active" if obj.is_active  else "Inactive"

    # ===== 6. CUSTOM SAVE LOGIC =====
    def create(self, validated_data: dict) -> State:
        """Custom create with audit logging"""
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)

    def update(self, instance: State, validated_data: dict) -> State:
        """Custom update handling"""
        # Prevent is_active toggle without permission
        if 'is_active' in validated_data and not self.context['request'].user.is_staff:
            raise PermissionDenied(
                "Only staff can change activation status"
            )
        return super().update(instance, validated_data)
