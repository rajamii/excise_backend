import logging
import re

from rest_framework import serializers

from auth.workflow.constants import WORKFLOW_IDS
from models.transactional.supply_chain.access_control import condition_role_matches

from .models import EnaRevalidationDetail


logger = logging.getLogger(__name__)


class EnaRevalidationDetailSerializer(serializers.ModelSerializer):
    allowed_actions = serializers.SerializerMethodField()
    allowed_action_configs = serializers.SerializerMethodField()
    establishment_name = serializers.SerializerMethodField()

    class Meta:
        model = EnaRevalidationDetail
        fields = '__all__'
        extra_kwargs = {
            'our_ref_no': {'required': False},
        }

    def _normalize_status_token(self, value):
        return re.sub(r'[^a-z0-9]+', '', str(value or '').lower())

    def _resolve_stage(self, obj, current_stage=None):
        stage = current_stage or getattr(obj, 'current_stage', None)
        if stage:
            return stage

        workflow_id = getattr(obj, 'workflow_id', None) or WORKFLOW_IDS['ENA_REVALIDATION']
        raw_status = str(getattr(obj, 'status', '') or '').strip()
        if not raw_status:
            return None

        from auth.workflow.models import WorkflowStage

        exact_stage = WorkflowStage.objects.filter(
            workflow_id=workflow_id,
            name=raw_status,
        ).first()
        if exact_stage:
            return exact_stage

        status_token = self._normalize_status_token(raw_status)
        if status_token.startswith('importpermitextends45days'):
            return WorkflowStage.objects.filter(
                workflow_id=workflow_id,
                name__istartswith='IMPORT PERMIT EXTENDS 45 DAYS',
            ).order_by('id').first()

        return None

    def _get_effective_status(self, obj, current_stage=None):
        stage = self._resolve_stage(obj, current_stage=current_stage)
        stage_name = str(getattr(stage, 'name', '') or '').strip()
        if stage_name:
            return stage_name
        return str(getattr(obj, 'status', '') or '')

    def _apply_stage_backed_status_defaults(self, validated_data):
        workflow = validated_data.get('workflow')
        current_stage = validated_data.get('current_stage')

        if workflow is None:
            from auth.workflow.models import Workflow

            workflow = Workflow.objects.filter(id=WORKFLOW_IDS['ENA_REVALIDATION']).first()
            if workflow is not None:
                validated_data['workflow'] = workflow

        if current_stage is None and workflow is not None:
            raw_status = str(validated_data.get('status', '') or '').strip()
            status_token = self._normalize_status_token(raw_status)

            from auth.workflow.models import WorkflowStage

            if raw_status:
                current_stage = WorkflowStage.objects.filter(
                    workflow=workflow,
                    name=raw_status,
                ).first()

            if current_stage is None and status_token.startswith('importpermitextends45days'):
                current_stage = WorkflowStage.objects.filter(
                    workflow=workflow,
                    name__istartswith='IMPORT PERMIT EXTENDS 45 DAYS',
                ).order_by('id').first()

            if current_stage is not None:
                validated_data['current_stage'] = current_stage

        current_stage = validated_data.get('current_stage')
        if current_stage is not None:
            validated_data['status'] = current_stage.name

        return validated_data

    def to_representation(self, instance):
        if hasattr(instance, 'sync_stage_backed_status'):
            _, changed_fields = instance.sync_stage_backed_status(persist=True)
            if changed_fields:
                instance.refresh_from_db(fields=['status', 'current_stage', 'workflow'])

        data = super().to_representation(instance)
        effective_status = self._get_effective_status(instance)
        data['status'] = effective_status
        data['current_stage_name'] = effective_status if getattr(instance, 'current_stage_id', None) else ''
        return data

    def get_establishment_name(self, obj):
        if obj.establishment_name:
            return obj.establishment_name

        if not obj.licensee_id:
            return obj.distillery_name or ''

        from models.masters.license.models import License

        try:
            license_obj = License.objects.filter(
                license_id=obj.licensee_id,
                is_active=True,
            ).select_related('source_content_type').first()

            if license_obj and license_obj.source_application:
                establishment_name = getattr(license_obj.source_application, 'establishment_name', None)
                if establishment_name:
                    return establishment_name
        except Exception as e:
            logger.warning(
                "Unable to resolve revalidation establishment_name for licensee_id=%s: %s",
                obj.licensee_id,
                e,
            )

        return obj.distillery_name or ''

    def get_allowed_actions(self, obj):
        request = self.context.get('request')
        effective_status = self._get_effective_status(obj)

        if not request or not request.user.is_authenticated:
            return []

        user_role_name = request.user.role.name if hasattr(request.user, 'role') and request.user.role else None
        if not user_role_name:
            return []

        user_role_name = user_role_name.strip()

        role = None
        commissioner_roles = ['level_1', 'level_2', 'level_3', 'level_4', 'level_5', 'Site-Admin', 'site_admin', 'commissioner', 'Commissioner']
        permit_roles = ['permit-section', 'Permit-Section', 'Permit Section', 'permit section']
        oic_roles = ['officer-in-charge', 'Officer-in-Charge', 'OIC', 'oic']
        licensee_roles = ['licensee', 'Licensee']

        if user_role_name in commissioner_roles:
            role = 'commissioner'
        elif user_role_name in permit_roles:
            role = 'permit-section'
        elif user_role_name in oic_roles:
            role = 'officer-in-charge'
        elif user_role_name in licensee_roles:
            role = 'licensee'

        if not role:
            return []

        from auth.workflow.models import WorkflowTransition

        current_stage = self._resolve_stage(obj, current_stage=obj.current_stage)
        if not current_stage:
            return []

        transitions = WorkflowTransition.objects.filter(from_stage=current_stage)
        actions = []
        for transition in transitions:
            cond = transition.condition or {}
            if condition_role_matches(cond, request.user):
                action = cond.get('action')
                if action:
                    actions.append(action)

        status_token = self._normalize_status_token(effective_status)
        current_stage_token = self._normalize_status_token(current_stage.name)
        if role == 'licensee' and (
            status_token.startswith('importpermitextends45days')
            or current_stage_token.startswith('importpermitextends45days')
        ):
            actions.append('REQUEST_REVALIDATION')

        workflow_id = getattr(obj, 'workflow_id', None)
        if role in ['commissioner', 'officer-in-charge']:
            if current_stage.name == 'ApprovedRevalidationByCommissioner' and workflow_id == 4:
                actions.append('VIEW_PERMIT_SLIP')

        return list(set(actions))

    def get_allowed_action_configs(self, obj):
        actions = self.get_allowed_actions(obj)
        if not actions:
            return []

        from auth.workflow.services import WorkflowService

        configs = []
        for action_name in actions:
            config = WorkflowService.get_action_config(action_name)
            configs.append(config)
        return configs

    def create(self, validated_data):
        validated_data.pop('our_ref_no', None)

        existing_refs = EnaRevalidationDetail.objects.values_list('our_ref_no', flat=True)
        pattern = r'REV/(\d+)/EXCISE'
        numbers = []

        for ref in existing_refs:
            match = re.match(pattern, str(ref or ''))
            if match:
                numbers.append(int(match.group(1)))

        next_number = (max(numbers) + 1) if numbers else 1
        validated_data['our_ref_no'] = f"REV/{next_number:02d}/EXCISE"

        request = self.context.get('request')
        if request:
            requested_licensee_id = request.data.get('licensee_id') or request.data.get('licenseeId')
            if requested_licensee_id:
                validated_data['licensee_id'] = requested_licensee_id

        if not validated_data.get('licensee_id') and request and hasattr(request.user, 'supply_chain_profile'):
            validated_data['licensee_id'] = request.user.supply_chain_profile.licensee_id
        elif not validated_data.get('licensee_id') and request and hasattr(request.user, 'manufacturing_units'):
            unit = request.user.manufacturing_units.exclude(licensee_id__isnull=True).exclude(licensee_id='').first()
            if unit:
                validated_data['licensee_id'] = unit.licensee_id

        if not validated_data.get('licensee_id'):
            raise serializers.ValidationError({
                'licensee_id': 'Unable to determine licensee mapping. Please set your active supply-chain profile and try again.'
            })

        if validated_data.get('licensee_id'):
            from models.masters.license.models import License

            try:
                license_obj = License.objects.filter(
                    license_id=validated_data['licensee_id'],
                    is_active=True,
                ).select_related('source_content_type').first()

                if license_obj and license_obj.source_application:
                    establishment_name = getattr(license_obj.source_application, 'establishment_name', None)
                    if establishment_name:
                        validated_data['establishment_name'] = establishment_name
            except Exception as e:
                logger.warning(
                    "Unable to store revalidation establishment_name for licensee_id=%s: %s",
                    validated_data.get('licensee_id'),
                    e,
                )

        validated_data = self._apply_stage_backed_status_defaults(validated_data)
        return super().create(validated_data)
