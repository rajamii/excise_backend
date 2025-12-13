from rest_framework import serializers
from .models import EnaCancellationDetail

class EnaCancellationDetailSerializer(serializers.ModelSerializer):
    allowed_actions = serializers.SerializerMethodField()

    class Meta:
        model = EnaCancellationDetail
        fields = '__all__'

    def get_allowed_actions(self, obj):
        request = self.context.get('request')
        if not request or not hasattr(request, 'user'):
            return []
        
        # Determine role (assuming simple mapping or from user object)
        # Using 'permit-section' as default for testing if logic is simple, 
        # but realistically should come from request.user.role or group
        # Determine role and normalize it to match WorkflowRule expected values
        user_role = getattr(request.user, 'role', 'permit-section')
        if not user_role:
            role = 'permit-section'
        elif 'permit section' in str(user_role).lower():
            role = 'permit-section'
        elif 'commissioner' in str(user_role).lower():
            role = 'commissioner'
        else:
            role = str(user_role)
            
        # Fallback for status_code if missing (legacy data)
        status_code = obj.status_code
        if not status_code:
            status_code = 'CN_00'
            
        from models.masters.supply_chain.status_master.models import WorkflowRule
        
        # DEBUG LOGGING
        print(f"DEBUG: Checking actions for Status: {status_code}, Role: {role}")
        
        actions = WorkflowRule.objects.filter(
            current_status__status_code=status_code,
            allowed_role=role
        ).values_list('action', flat=True)
        
        print(f"DEBUG: Found actions: {list(actions)}")
        
        return list(actions)

class CancellationCreateSerializer(serializers.Serializer):
    reference_no = serializers.CharField(max_length=100)
    permit_numbers = serializers.ListField(child=serializers.CharField(max_length=100))
    licensee_id = serializers.CharField(max_length=50)

