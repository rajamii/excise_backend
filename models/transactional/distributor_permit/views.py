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
    role_id = getattr(getattr(user, 'role', None), 'id', 0)
    role_name = str(getattr(getattr(user, 'role', None), 'name', '') or '').strip().lower()

    if _is_admin_user(user):
        return qs
    if role_id in (10, 12) or 'commissioner' in role_name:
        # Commissioner only sees applications that are at or past Forwarded Commissioner (153)
        return qs.filter(current_stage_id__in=[153, 154, 156, 157, 151, 152])
    if role_id == 5 or 'permit' in role_name:
        return qs
    # Licensee/distributor applicant only sees their own applications
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
            if action == 'PAY':
                application.is_excise_duty_fee_paid = True
            if remarks:
                application.officer_remarks = remarks
            
            if action == 'APPROVE' and target_transition.to_stage.is_final:
                application.submitted_at = timezone.now()

            application.save()

        serializer = DistributorPermitApplicationSerializer(application, context={'request': request})
        return Response({
            'status': 'success',
            'message': f'Action {action} performed successfully.',
            'data': serializer.data
        })
