 # serializers/state_serializer.py
from rest_framework import serializers
from django.core.validators import MinValueValidator, MaxValueValidator
from rest_framework.exceptions import PermissionDenied
from models.masters.core.models import State
from django.utils import timezone

class StateSerializer(serializers.ModelSerializer):
    # ===== 1. DECLARED FIELDS (Custom behavior) =====
    status = serializers.SerializerMethodField(read_only=True)
    StateCode = serializers.IntegerField(
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
            'State',
            'StateNameLL',
            'StateCode',
            'IsActive',
            'status'  # Computed field
        ]
        extra_kwargs = {
            'StateNameLL': {
                'error_messages': {
                    'blank': 'Local language name cannot be empty',
                    'null': 'Local language name cannot be null'
                }
            }
        }

    # ===== 3. FIELD VALIDATORS =====
    def validate_StateCode(self, value: int) -> int:
        """Ensure state code is unique (excluding current instance)"""
        queryset = State.objects.filter(StateCode=value)
        
        # During updates, exclude current instance
        if self.instance and self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
            
        if queryset.exists():
            raise serializers.ValidationError("This state code is already in use")
        return value

    def validate_StateNameLL(self, value: str) -> str:
        """Clean local language name"""
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError(
                "Local name must be at least 2 characters"
            )
        return value

    # ===== 4. OBJECT VALIDATION =====
    def validate(self, attrs: dict) -> dict:
        """Cross-field validation"""
        # Ensure state name doesn't match local name
        if 'State' in attrs and 'StateNameLL' in attrs:
            if attrs['State'].lower() == attrs['StateNameLL'].lower():
                raise serializers.ValidationError(
                    "State name cannot match local language name"
                )
        
        # Auto-set modified timestamp
        attrs['last_modified'] = timezone.now()
        
        return attrs

    # ===== 5. COMPUTED FIELDS =====
    def get_status(self, obj) -> str:
        """Dynamic status field"""
        return "Active" if obj.IsActive else "Inactive"

    # ===== 6. CUSTOM SAVE LOGIC =====
    def create(self, validated_data: dict) -> State:
        """Custom create with audit logging"""
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)

    def update(self, instance: State, validated_data: dict) -> State:
        """Custom update handling"""
        # Prevent IsActive toggle without permission
        if 'IsActive' in validated_data and not self.context['request'].user.is_staff:
            raise PermissionDenied(
                "Only staff can change activation status"
            )
        return super().update(instance, validated_data)
