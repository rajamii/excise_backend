from rest_framework import serializers
from .models import EnaBulkSpiritUsage
from auth.workflow.constants import WORKFLOW_IDS
from auth.workflow.models import WorkflowTransition


class EnaBulkSpiritUsageSerializer(serializers.ModelSerializer):
    applicant_name = serializers.SerializerMethodField()
    current_stage_name = serializers.CharField(source='current_stage.name', read_only=True, default='')
    allowed_actions = serializers.SerializerMethodField()

    class Meta:
        model = EnaBulkSpiritUsage
        fields = [
            'id',
            'reference_no',
            'licensee_id',
            'distillery_name',
            'applicant',
            'applicant_name',
            'bulk_spirit_type',
            'quantity',
            'purpose',
            'remarks',
            'status',
            'status_code',
            'rejection_reason',
            'workflow',
            'current_stage',
            'current_stage_name',
            'reviewed_by',
            'reviewed_at',
            'created_at',
            'updated_at',
            'allowed_actions',
        ]
        read_only_fields = [
            'id',
            'reference_no',
            'applicant',
            'status',
            'status_code',
            'rejection_reason',
            'workflow',
            'current_stage',
            'reviewed_by',
            'reviewed_at',
            'created_at',
            'updated_at',
        ]

    def get_applicant_name(self, obj) -> str:
        if not obj.applicant:
            return obj.distillery_name or 'Licensee'
        first = str(getattr(obj.applicant, 'first_name', '') or '').strip()
        last = str(getattr(obj.applicant, 'last_name', '') or '').strip()
        name = f'{first} {last}'.strip()
        return name or getattr(obj.applicant, 'username', '') or 'Licensee'

    def get_allowed_actions(self, obj) -> list:
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            return []

        user = request.user
        role_name = str(getattr(getattr(user, 'role', None), 'name', '') or '').lower()
        is_oic = 'officerincharge' in role_name or 'oic' in role_name or hasattr(user, 'oic_assignment')

        if not is_oic:
            return ['VIEW']

        if obj.status.lower() in ['pending', 'pending oic approval', 'pending approval']:
            return ['VIEW', 'APPROVE', 'REJECT']

        return ['VIEW']
