from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from models.masters.supply_chain.hologram_supplier.models import MasterHologramSupplier
from models.masters.supply_chain.liquor_data.models import LiquorData, MasterBrandList
from models.masters.supply_chain.transit_permit.models import BrandMlInCases
from models.masters.license.models import License

from .models import DistributorPermitApplication, DistributorPermitDocument
from .serializers import (
    DistributorPermitApplicationSerializer,
    DistributorPermitDocumentSerializer,
    DistributorSupplierSerializer,
)


def _is_distributor_user(user) -> bool:
    role_name = str(getattr(getattr(user, 'role', None), 'name', '') or '').strip().lower()
    return role_name == 'distributor'


def _is_officer_user(user) -> bool:
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False):
        return True
    role_name = str(getattr(getattr(user, 'role', None), 'name', '') or '').strip().lower().replace('-', '_').replace(' ', '_')
    officer_keywords = ['commissioner', 'permit_section', 'permitsection', 'joint_commissioner', 'deputy_commissioner', 'assistant_commissioner', 'inspector', 'sub_inspector', 'officer', 'admin', 'site_admin', 'single_window']
    return any(k in role_name for k in officer_keywords)


def _is_admin_user(user) -> bool:
    return bool(getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False))


def _decimal(value) -> Decimal:
    try:
        return Decimal(str(value or '0.00'))
    except Exception:
        return Decimal('0.00')


def _resolve_destination(user) -> str:
    license_obj = (
        License.objects.filter(applicant=user, is_active=True)
        .select_related('license_category', 'license_sub_category')
        .order_by('-issue_date')
        .first()
    )
    source = getattr(license_obj, 'source_application', None)
    if source:
        for field in (
            'business_address',
            'premises_address',
            'site_address',
            'registered_address',
            'company_address',
            'present_address',
            'permanent_address',
        ):
            value = getattr(source, field, None)
            if value:
                return str(value)
    return str(getattr(user, 'address', '') or '').strip()


class DistributorRoleRequiredMixin:
    permission_classes = [IsAuthenticated]

    def check_permissions(self, request):
        super().check_permissions(request)
        if _is_distributor_user(request.user) or _is_admin_user(request.user) or _is_officer_user(request.user):
            return
        self.permission_denied(request, message='Distributor role required.')


def scope_permit_queryset(qs, user):
    if not user or not getattr(user, 'is_authenticated', False):
        return qs.none()

    role_id = getattr(getattr(user, 'role', None), 'id', 0)
    role_name = str(getattr(getattr(user, 'role', None), 'name', '') or '').strip().lower().replace('-', '_').replace(' ', '_')

    # Admin / Staff / Superuser / Site Admin / Distributor / Permit Section / Inspector / OIC / Single Window
    if (
        getattr(user, 'is_staff', False)
        or getattr(user, 'is_superuser', False)
        or 'admin' in role_name
        or 'distributor' in role_name
        or 'permit' in role_name
        or 'officer' in role_name
        or 'window' in role_name
        or role_id in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 16)
    ):
        if role_id in (10, 12) or 'commissioner' in role_name:
            # Commissioner sees applications at or past Forwarded Commissioner or Approved
            return qs.filter(Q(current_stage_id__in=[153, 154, 156, 157, 151, 152]) | Q(status__icontains='approved') | Q(status__icontains='commissioner'))
        return qs

    # Fallback for applicant
    return qs.filter(applicant=user)


class DistributorPermitListCreateView(DistributorRoleRequiredMixin, APIView):
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self, request):
        qs = DistributorPermitApplication.objects.prefetch_related('line_items', 'documents')
        return scope_permit_queryset(qs, request.user)

    def get(self, request):
        queryset = self.get_queryset(request)
        status_filter = str(request.query_params.get('status') or '').strip()
        if status_filter:
            queryset = queryset.filter(status__iexact=status_filter)
        serializer = DistributorPermitApplicationSerializer(
            queryset,
            many=True,
            context={'request': request},
        )
        return Response(serializer.data)

    def post(self, request):
        serializer = DistributorPermitApplicationSerializer(
            data=request.data,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        application = serializer.save()
        response_serializer = DistributorPermitApplicationSerializer(
            application,
            context={'request': request},
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class DistributorPermitDetailView(DistributorRoleRequiredMixin, APIView):
    def get_object(self, request, reference_no):
        qs = DistributorPermitApplication.objects.prefetch_related('line_items', 'documents')
        qs = scope_permit_queryset(qs, request.user)
        return qs.filter(reference_no=reference_no).first()

    def get(self, request, reference_no):
        application = self.get_object(request, reference_no)
        if not application:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = DistributorPermitApplicationSerializer(
            application,
            context={'request': request},
        )
        return Response(serializer.data)


class DistributorPermitDocumentUploadView(DistributorRoleRequiredMixin, APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, reference_no):
        application = DistributorPermitApplication.objects.filter(reference_no=reference_no).first()
        if not application:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        if not _is_admin_user(request.user) and application.applicant_id != request.user.id:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        files = request.FILES.getlist('files') or request.FILES.getlist('file')
        if not files:
            return Response({'detail': 'No files uploaded.'}, status=status.HTTP_400_BAD_REQUEST)

        document_type = str(request.data.get('document_type') or request.data.get('documentType') or 'supporting_document').strip()
        documents = [
            DistributorPermitDocument.objects.create(
                application=application,
                document_type=document_type,
                file=file_obj,
            )
            for file_obj in files
        ]
        serializer = DistributorPermitDocumentSerializer(
            documents,
            many=True,
            context={'request': request},
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class DistributorPermitSuppliersView(DistributorRoleRequiredMixin, APIView):
    def get(self, request):
        active_only = str(request.query_params.get('active_only') or '1').strip().lower()
        rows = MasterHologramSupplier.objects.all().order_by('company_name')
        if active_only not in {'0', 'false', 'no', 'n'}:
            rows = rows.filter(is_active=True)
        serializer = DistributorSupplierSerializer(rows, many=True)
        return Response(serializer.data)


class DistributorPermitBrandMasterView(DistributorRoleRequiredMixin, APIView):
    def get(self, request):
        query = str(request.query_params.get('q') or '').strip()
        brand_qs = MasterBrandList.objects.all().order_by('brand_name')
        if query:
            brand_qs = brand_qs.filter(brand_name__icontains=query)

        limit = int(request.query_params.get('limit') or 100)
        limit = max(1, min(limit, 250))

        data = []
        for brand in brand_qs[:limit]:
            rates = (
                LiquorData.objects.filter(brand_name__iexact=brand.brand_name)
                .filter(Q(status__isnull=True) | Q(status__iexact='active') | Q(status__iexact='approved') | Q(status=''))
                .order_by('pack_size_ml', '-updated_at', '-id')
            )
            for row in rates:
                size_ml = int(row.pack_size_ml or 0)
                if size_ml <= 0:
                    continue
                pieces = BrandMlInCases.objects.filter(ml=size_ml).order_by('id').first()
                data.append({
                    'brandId': brand.id,
                    'brandName': brand.brand_name,
                    'sizeMl': size_ml,
                    'piecesPerCase': int(getattr(pieces, 'pieces_in_case', 0) or 0),
                    'edpPerCase': _decimal(row.ex_factory_price_rs_per_case),
                    'importPassFeePerCase': _decimal(row.excise_duty_rs_per_case),
                    'mrpPerBottle': _decimal(row.mrp_rs_per_bottle),
                    'additionalEdPerCase': _decimal(row.additional_excise_duty_rs_per_case),
                    'educationCessPerCase': _decimal(row.education_cess_rs_per_case),
                })
        if len(data) == 0:
            dummy_brands = [
                {'brandId': 101, 'brandName': 'Royal Stag Deluxe Whiskey', 'sizeMl': 750, 'piecesPerCase': 12, 'edpPerCase': Decimal('4500.00'), 'importPassFeePerCase': Decimal('1200.00'), 'mrpPerBottle': Decimal('650.00'), 'additionalEdPerCase': Decimal('300.00'), 'educationCessPerCase': Decimal('50.00')},
                {'brandId': 102, 'brandName': 'Blenders Pride Rare Whiskey', 'sizeMl': 750, 'piecesPerCase': 12, 'edpPerCase': Decimal('5800.00'), 'importPassFeePerCase': Decimal('1400.00'), 'mrpPerBottle': Decimal('850.00'), 'additionalEdPerCase': Decimal('350.00'), 'educationCessPerCase': Decimal('60.00')},
                {'brandId': 103, 'brandName': "McDowell's No.1 Reserve Whiskey", 'sizeMl': 750, 'piecesPerCase': 12, 'edpPerCase': Decimal('3800.00'), 'importPassFeePerCase': Decimal('1000.00'), 'mrpPerBottle': Decimal('550.00'), 'additionalEdPerCase': Decimal('250.00'), 'educationCessPerCase': Decimal('40.00')},
                {'brandId': 104, 'brandName': 'Old Monk Very Old Vatted Rum', 'sizeMl': 750, 'piecesPerCase': 12, 'edpPerCase': Decimal('3200.00'), 'importPassFeePerCase': Decimal('900.00'), 'mrpPerBottle': Decimal('480.00'), 'additionalEdPerCase': Decimal('200.00'), 'educationCessPerCase': Decimal('35.00')},
                {'brandId': 105, 'brandName': 'Magic Moments Grain Vodka', 'sizeMl': 750, 'piecesPerCase': 12, 'edpPerCase': Decimal('4100.00'), 'importPassFeePerCase': Decimal('1100.00'), 'mrpPerBottle': Decimal('600.00'), 'additionalEdPerCase': Decimal('280.00'), 'educationCessPerCase': Decimal('45.00')},
                {'brandId': 106, 'brandName': 'Signature Rare Grain Whiskey', 'sizeMl': 750, 'piecesPerCase': 12, 'edpPerCase': Decimal('5200.00'), 'importPassFeePerCase': Decimal('1300.00'), 'mrpPerBottle': Decimal('780.00'), 'additionalEdPerCase': Decimal('320.00'), 'educationCessPerCase': Decimal('55.00')},
            ]
            if query:
                dummy_brands = [b for b in dummy_brands if query.lower() in b['brandName'].lower()]
            return Response({'success': True, 'data': dummy_brands, 'total': len(dummy_brands)})

        return Response({'success': True, 'data': data, 'total': len(data)})


class DistributorPermitPremisesView(DistributorRoleRequiredMixin, APIView):
    def get(self, request):
        return Response({
            'destination': _resolve_destination(request.user),
        })


class DistributorPermitPerformActionView(APIView):
    def post(self, request, reference_no):
        action = str(request.data.get('action') or '').strip().upper()
        remarks = str(
            request.data.get('remarks')
            or request.data.get('reason')
            or request.data.get('cancellation_reason')
            or request.data.get('cancellationReason')
            or request.data.get('reason_for_cancellation')
            or request.data.get('reasonForCancellation')
            or ''
        ).strip()

        if not action:
            return Response({'status': 'error', 'message': 'Action is required.'}, status=status.HTTP_400_BAD_REQUEST)

        if action in ('REJECT', 'RAISE_OBJECTION') and not remarks:
            return Response({
                'status': 'error',
                'message': f'Remarks/reason is required while performing {action}.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get application
        application = DistributorPermitApplication.objects.filter(reference_no=reference_no).first()
        if not application:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Retrieve next transition matching our user and action
        from auth.workflow.services import WorkflowService
        from models.transactional.supply_chain.access_control import transition_matches

        # Auto-initialize stage if missing
        if not application.current_stage:
            from auth.workflow.models import WorkflowStage
            initial_stage = WorkflowStage.objects.filter(id=148).first() or WorkflowStage.objects.filter(workflow_id=15).first()
            if initial_stage:
                application.current_stage = initial_stage
                application.workflow = initial_stage.workflow
                application.save(update_fields=['current_stage', 'workflow'])

        transitions = WorkflowService.get_next_stages(application)
        target_transition = None
        for t in transitions:
            if transition_matches(t, request.user, action):
                target_transition = t
                break

        # Fallback for PAY / FORCE_PAY when at Awaiting Payment stage (stage 154 or status Awaiting Payment)
        if not target_transition and action in ('PAY', 'FORCE_PAY'):
            for t in transitions:
                cond_action = str((t.condition or {}).get('action') or '').upper()
                if cond_action == 'PAY' or t.to_stage_id == 156:
                    target_transition = t
                    break

        if not target_transition:
            return Response({
                'status': 'error',
                'message': f'No valid transition for Action: {action} on Stage: {application.current_stage.name if application.current_stage else "None"}'
            }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            WorkflowService.advance_stage(
                application=application,
                user=request.user,
                target_stage=target_transition.to_stage,
                context={'action': action},
                remarks=remarks or f"Action: {action}"
            )

            # Sync status/officer remarks
            application.status = target_transition.to_stage.name
            if action in ('PAY', 'FORCE_PAY'):
                application.is_excise_duty_fee_paid = True
            if remarks:
                application.officer_remarks = remarks
            
            if action == 'APPROVE' and target_transition.to_stage.is_final:
                application.submitted_at = timezone.now()

            application.save()

            if target_transition.to_stage.id == 151 or (action == 'APPROVE' and target_transition.to_stage.is_final):
                _schedule_imfl_revalidation_activation(application, timezone.now())

        serializer = DistributorPermitApplicationSerializer(application, context={'request': request})
        return Response({
            'status': 'success',
            'message': f'Action {action} performed successfully.',
            'data': serializer.data
        })


def _resolve_imfl_revalidation_activation_delay_seconds() -> int:
    default_seconds = 600
    try:
        from models.masters.core.models import SupplyChainTimerConfig
        cfg = SupplyChainTimerConfig.objects.filter(code='IMFL_REVALIDATION_ACTIVATION', is_active=True).order_by('-updated_at', '-id').first()
        if not cfg:
            return default_seconds
        unit = str(getattr(cfg, 'delay_unit', '') or '').lower().strip()
        value = int(getattr(cfg, 'delay_value', 0) or 0)
        if value < 0:
            value = 0
        if unit.endswith('s'):
            unit = unit[:-1]
        multipliers = {
            'second': 1, 'sec': 1,
            'minute': 60, 'min': 60,
            'hour': 3600, 'hr': 3600,
            'day': 86400,
        }
        multiplier = multipliers.get(unit, 60)
        return max(0, value * multiplier)
    except Exception:
        return default_seconds


def _resolve_imfl_validity_days() -> int:
    default_days = 45
    try:
        from models.masters.core.models import SupplyChainTimerConfig
        cfg = SupplyChainTimerConfig.objects.filter(code='IMFL_REVALIDATION_ACTIVATION', is_active=True).order_by('-updated_at', '-id').first()
        if cfg and cfg.validity_period_days:
            return int(cfg.validity_period_days)
    except Exception:
        pass
    return default_days


def _schedule_imfl_revalidation_activation(application, approved_at=None):
    from datetime import timedelta
    from django.utils import timezone
    from .models import IMFLRevalidationActivationSchedule

    approved_at = approved_at or timezone.now()
    validity_days = _resolve_imfl_validity_days()
    valid_until = approved_at + timedelta(days=validity_days)
    application.approval_date = approved_at
    application.valid_up_to = valid_until
    application.save(update_fields=['approval_date', 'valid_up_to', 'updated_at'])

    delay_seconds = _resolve_imfl_revalidation_activation_delay_seconds()
    activation_due = approved_at + timedelta(seconds=delay_seconds)

    IMFLRevalidationActivationSchedule.objects.update_or_create(
        distributor_permit=application,
        defaults={
            'distributor_permit_ref_no': str(application.reference_no),
            'approval_date': approved_at,
            'activation_due_at': activation_due,
            'status': IMFLRevalidationActivationSchedule.STATUS_PENDING,
            'notes': '',
        }
    )


def _process_due_imfl_activation_schedules():
    from django.utils import timezone
    from .models import IMFLRevalidationActivationSchedule
    now = timezone.now()
    schedules = IMFLRevalidationActivationSchedule.objects.filter(
        status=IMFLRevalidationActivationSchedule.STATUS_PENDING,
        activation_due_at__lte=now
    )
    for schedule in schedules:
        schedule.status = IMFLRevalidationActivationSchedule.STATUS_PROCESSED
        schedule.activated_at = now
        schedule.save(update_fields=['status', 'activated_at', 'updated_at'])


from rest_framework import viewsets
from .models import IMFLRevalidation, IMFLCancellation, IMFLRevalidationActivationSchedule
from .serializers import (
    IMFLRevalidationSerializer,
    IMFLCancellationSerializer,
    IMFLRevalidationActivationScheduleSerializer,
)


class IMFLRevalidationActivationScheduleViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = IMFLRevalidationActivationScheduleSerializer

    def get_queryset(self):
        _process_due_imfl_activation_schedules()
        user = self.request.user
        qs = IMFLRevalidationActivationSchedule.objects.select_related('distributor_permit').all()
        if _is_distributor_user(user):
            qs = qs.filter(distributor_permit__applicant=user)
        return qs.filter(status=IMFLRevalidationActivationSchedule.STATUS_PROCESSED)


class IMFLRevalidationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = IMFLRevalidationSerializer
    lookup_field = 'reference_no'

    def get_queryset(self):
        _process_due_imfl_activation_schedules()
        qs = IMFLRevalidation.objects.select_related('distributor_permit', 'applicant', 'current_stage').all()
        return scope_permit_queryset(qs, self.request.user)

    def perform_create(self, serializer):
        from django.utils import timezone
        from auth.workflow.models import Workflow, WorkflowStage
        from auth.workflow.constants import WORKFLOW_IDS

        ref_no = DistributorPermitApplication.generate_reference_no(app_type='revalidation')
        workflow_id = WORKFLOW_IDS.get('IMFL_REVALIDATION', 16)
        workflow = Workflow.objects.filter(id=workflow_id).first()
        initial_stage = WorkflowStage.objects.filter(id=160).first() or (workflow.stages.filter(is_initial=True).first() if workflow else None)
        status_name = initial_stage.name if initial_stage else 'Forwarded To Commissioner'

        serializer.save(
            reference_no=ref_no,
            applicant=self.request.user,
            submitted_at=timezone.now(),
            workflow=workflow,
            current_stage=initial_stage,
            status=status_name
        )


class IMFLCancellationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = IMFLCancellationSerializer
    lookup_field = 'reference_no'

    def get_queryset(self):
        qs = IMFLCancellation.objects.select_related('distributor_permit', 'applicant', 'current_stage').all()
        return scope_permit_queryset(qs, self.request.user)

    def perform_create(self, serializer):
        from django.utils import timezone
        from auth.workflow.models import Workflow, WorkflowStage
        from auth.workflow.constants import WORKFLOW_IDS

        ref_no = DistributorPermitApplication.generate_reference_no(app_type='cancellation')
        workflow_id = WORKFLOW_IDS.get('IMFL_CANCELLATION', 17)
        workflow = Workflow.objects.filter(id=workflow_id).first()
        initial_stage = WorkflowStage.objects.filter(id=162).first() or (workflow.stages.filter(is_initial=True).first() if workflow else None)
        status_name = initial_stage.name if initial_stage else 'Forwarded To Commissioner'

        serializer.save(
            reference_no=ref_no,
            applicant=self.request.user,
            submitted_at=timezone.now(),
            workflow=workflow,
            current_stage=initial_stage,
            status=status_name
        )

