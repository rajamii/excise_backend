from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from models.transactional.dashboard_cache import dashboard_counts_cache, invalidate_dashboard_counts_cache
from models.masters.supply_chain.hologram_supplier.models import MasterHologramSupplier
from models.masters.supply_chain.liquor_data.models import LiquorData, MasterBrandList
from models.masters.supply_chain.transit_permit.models import BrandMlInCases
from models.masters.license.models import License

from .models import DistributorPermitApplication, DistributorPermitDocument, IMFLRevalidation, IMFLCancellation, IMFLArrival, IMFLCasesProcessed
from .serializers import (
    DistributorPermitApplicationSerializer,
    DistributorPermitDocumentSerializer,
    DistributorSupplierSerializer,
    IMFLArrivalSerializer,
    IMFLCasesProcessedSerializer,
)


def _is_distributor_user(user) -> bool:
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    role_id = getattr(getattr(user, 'role', None), 'id', 0)
    role_name = str(getattr(getattr(user, 'role', None), 'name', '') or '').strip().lower()
    if role_name in ('distributor', 'licensee', 'licencee') or role_id in (1, 2, 16):
        return True
    try:
        from models.masters.license.models import License
        return License.objects.filter(applicant=user, license_category__is_distributor_user=True, is_active=True).exists()
    except Exception:
        pass
    return False


def _is_officer_user(user) -> bool:
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False):
        return True
    role_id = getattr(getattr(user, 'role', None), 'id', 0)
    if role_id in (5, 6, 7, 8, 9, 10, 12):
        return True
    role_name = str(getattr(getattr(user, 'role', None), 'name', '') or '').strip().lower().replace('-', '_').replace(' ', '_')
    officer_keywords = ['commissioner', 'permit_section', 'permitsection', 'joint_commissioner', 'deputy_commissioner', 'assistant_commissioner', 'inspector', 'sub_inspector', 'officer', 'offcier', 'oic', 'admin', 'site_admin', 'single_window']
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

    # Admin / Staff / Superuser / Site Admin
    if getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False) or 'admin' in role_name or role_id == 15:
        return qs

    # Officers (Commissioner, Permit Section, OIC)
    is_commissioner = 'commissioner' in role_name or role_id in (10, 12)
    is_permit_section = 'permit' in role_name or role_id in (5, 6)
    is_oic = 'oic' in role_name or 'officer' in role_name or getattr(user, 'is_oic_managed', False)

    if is_commissioner:
        return qs.filter(Q(current_stage_id__in=[153, 154, 156, 157, 151, 152]) | Q(status__icontains='approved') | Q(status__icontains='commissioner'))

    if is_permit_section or is_oic:
        assignment = getattr(user, 'oic_assignment', None)
        if assignment and getattr(assignment, 'assignment_type', '') == 'distributor' and getattr(assignment, 'distributor_user', None):
            return qs.filter(applicant=assignment.distributor_user)
        return qs

    # For all applicant / licensee / distributor users: scope strictly to their own applications!
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


def _normalize_imfl_dashboard_tab(raw_tab):
    tab = str(raw_tab or 'requisition').strip().lower().replace('_', '-')
    if tab in ('revalidation', 'imfl-revalidation', 'distributor-permit-revalidation'):
        return 'revalidation'
    if tab in ('cancellation', 'imfl-cancellation', 'distributor-permit-cancellation'):
        return 'cancellation'
    return 'requisition'


def _imfl_dashboard_queryset(request, tab):
    if tab == 'revalidation':
        qs = IMFLRevalidation.objects.select_related('applicant', 'current_stage', 'distributor_permit')
    elif tab == 'cancellation':
        qs = IMFLCancellation.objects.select_related('applicant', 'current_stage', 'distributor_permit')
    else:
        qs = DistributorPermitApplication.objects.select_related('applicant', 'current_stage').all()
    return scope_permit_queryset(qs, request.user)


def _stage_text(item):
    stage_name = getattr(getattr(item, 'current_stage', None), 'name', '') or ''
    return f"{getattr(item, 'status', '') or ''} {stage_name}".strip().lower()


def _is_final_imfl_item(item):
    text = _stage_text(item)
    return any(token in text for token in ('approved', 'rejected', 'cancelled', 'canceled', 'completed'))


def _is_objection_imfl_item(item):
    return 'objection' in _stage_text(item)


def _is_awaiting_payment_imfl_item(item):
    text = _stage_text(item).replace('_', ' ')
    return 'awaiting payment' in text or ('payment' in text and 'completed' not in text and 'paid' not in text)


def _is_item_pending_for_user(item, user):
    role_name = str(getattr(getattr(user, 'role', None), 'name', '') or '').lower()
    role_id = getattr(getattr(user, 'role', None), 'id', 0)
    is_commissioner = 'commissioner' in role_name or role_id == 10
    is_permit_section = 'permit' in role_name or 'oic' in role_name or role_id in (5, 6)

    text = _stage_text(item)
    stage_id = getattr(item, 'current_stage_id', None) or getattr(getattr(item, 'current_stage', None), 'id', None)

    is_commissioner_stage = stage_id in (153, 157, 160, 162, 163) or 'commissioner' in text
    is_permit_section_stage = stage_id in (148, 147, 149, 155, 156) or 'permit' in text or 'oic' in text

    if is_permit_section:
        if is_commissioner_stage:
            return False  # Under Process for Permit Section
        if is_permit_section_stage:
            return True   # Pending for Permit Section
    elif is_commissioner:
        if is_permit_section_stage or stage_id == 154 or 'payment' in text or 'awaiting' in text:
            return False  # Under Process for Commissioner
        if is_commissioner_stage:
            return True   # Pending for Commissioner

    return True


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@dashboard_counts_cache("distributor_permit")
def dashboard_counts(request):
    tab = _normalize_imfl_dashboard_tab(request.query_params.get('tab'))
    qs = _imfl_dashboard_queryset(request, tab)

    month = request.query_params.get('month')
    year = request.query_params.get('year')
    date_field = 'submitted_at' if tab in ('revalidation', 'cancellation') else 'created_at'
    if month:
        qs = qs.filter(**{f'{date_field}__month': month})
    if year:
        qs = qs.filter(**{f'{date_field}__year': year})

    items = list(qs)
    approved = sum(1 for item in items if _is_final_imfl_item(item) and 'approved' in _stage_text(item))
    rejected = sum(1 for item in items if 'rejected' in _stage_text(item))
    objection = sum(1 for item in items if _is_objection_imfl_item(item))
    awaiting_payment = sum(1 for item in items if _is_awaiting_payment_imfl_item(item))

    pending = 0
    under_process = 0
    for item in items:
        if _is_final_imfl_item(item) or _is_objection_imfl_item(item):
            continue
        if _is_item_pending_for_user(item, request.user):
            pending += 1
        else:
            under_process += 1

    return Response({
        'tab': tab,
        'applied': len(items),
        'total': len(items),
        'pending': pending,
        'under_process': under_process,
        'underProcess': under_process,
        'objection': objection,
        'approved': approved,
        'rejected': rejected,
        'awaiting_payment': awaiting_payment,
        'awaitingPayment': awaiting_payment,
    }, status=status.HTTP_200_OK)


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
        from .models import IMFLSupplier
        suppliers = IMFLSupplier.objects.all().order_by('id')
        if suppliers.exists():
            data = [
                {
                    'id': s.id,
                    'supplier_master_name': s.supplier_master_name or s.supplier_name,
                    'supplierMasterName': s.supplier_master_name or s.supplier_name,
                    'supplier_name': s.supplier_master_name or s.supplier_name,
                    'company_name': s.supplier_name,
                    'companyName': s.supplier_name,
                    'address': s.address,
                    'route_details': s.route_details,
                    'routeDetails': s.route_details,
                    'state': s.address.split(',')[-1].strip() if ',' in s.address else '',
                }
                for s in suppliers
            ]
            return Response(data)

        active_only = str(request.query_params.get('active_only') or '1').strip().lower()
        rows = MasterHologramSupplier.objects.all().order_by('company_name')
        if active_only not in {'0', 'false', 'no', 'n'}:
            rows = rows.filter(is_active=True)
        serializer = DistributorSupplierSerializer(rows, many=True)
        return Response(serializer.data)


class DistributorPermitBrandMasterView(DistributorRoleRequiredMixin, APIView):
    def get(self, request):
        from .models import IMFLBrand
        query = str(request.query_params.get('q') or '').strip()
        supplier_id = request.query_params.get('supplier_id') or request.query_params.get('supplierId')

        imfl_qs = IMFLBrand.objects.select_related('supplier').all().order_by('brand_name')
        if query:
            imfl_qs = imfl_qs.filter(brand_name__icontains=query)
        if supplier_id:
            imfl_qs = imfl_qs.filter(supplier_id=supplier_id)

        if imfl_qs.exists():
            data = [
                {
                    'brandId': b.id,
                    'brandName': b.brand_name,
                    'sizeMl': b.size_ml,
                    'piecesPerCase': b.pieces_per_case,
                    'edpPerCase': b.edp_per_case,
                    'importPassFeePerCase': b.import_pass_fee_per_case,
                    'mrpPerBottle': b.mrp_per_bottle,
                    'additionalEdPerCase': b.additional_ed_per_case,
                    'educationCessPerCase': b.education_cess_per_case,
                    'supplierId': b.supplier_id,
                    'supplierName': b.supplier.supplier_name if b.supplier else '',
                }
                for b in imfl_qs
            ]
            return Response({'success': True, 'data': data, 'total': len(data)})

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

        # Get application (check Cancellation, Revalidation, or Permit Application)
        application = (
            IMFLCancellation.objects.filter(reference_no=reference_no).first()
            or IMFLRevalidation.objects.filter(reference_no=reference_no).first()
            or DistributorPermitApplication.objects.filter(reference_no=reference_no).first()
        )
        if not application:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Retrieve next transition matching our user and action
        from auth.workflow.services import WorkflowService
        from models.transactional.supply_chain.access_control import transition_matches

        # Auto-initialize stage/workflow if missing
        if not application.current_stage or not application.workflow:
            from auth.workflow.models import Workflow, WorkflowStage
            from auth.workflow.constants import WORKFLOW_IDS
            wf_key = 'IMFL_CANCELLATION' if isinstance(application, IMFLCancellation) else ('IMFL_REVALIDATION' if isinstance(application, IMFLRevalidation) else 'IMFL_REQUISITION')
            wf = Workflow.objects.filter(id=WORKFLOW_IDS.get(wf_key, 17)).first()
            if wf and not application.workflow:
                application.workflow = wf
            if not application.current_stage:
                initial_stage = WorkflowStage.objects.filter(id=162 if isinstance(application, IMFLCancellation) else 148).first()
                if initial_stage:
                    application.current_stage = initial_stage
            application.save(update_fields=['current_stage', 'workflow'])

        transitions = WorkflowService.get_next_stages(application)
        target_transition = None
        for t in transitions:
            cond_act = str((t.condition or {}).get('action') or '').upper()
            if cond_act == action or transition_matches(t, request.user, action) or (action == 'APPROVE' and cond_act in ('APPROVE', 'APPROVEPAYSLIP')):
                target_transition = t
                break

        # Fallback for PAY / FORCE_PAY when at Awaiting Payment stage (stage 154 or status Awaiting Payment)
        if not target_transition and action in ('PAY', 'FORCE_PAY'):
            for t in transitions:
                cond_action = str((t.condition or {}).get('action') or '').upper()
                if cond_action == 'PAY' or t.to_stage_id == 156:
                    target_transition = t
                    break

        # Fallback transition for Commissioner APPROVE on Cancellation (stage 162 -> 165)
        if not target_transition and action == 'APPROVE' and isinstance(application, IMFLCancellation):
            from auth.workflow.models import WorkflowStage, WorkflowTransition
            stage_165 = WorkflowStage.objects.filter(id=165).first() or WorkflowStage.objects.filter(name='Approved By Commissioner', workflow_id=17).first()
            if stage_165:
                target_transition = WorkflowTransition(
                    workflow=application.workflow,
                    from_stage=application.current_stage,
                    to_stage=stage_165,
                    condition={'role': 'commissioner', 'action': 'APPROVE'}
                )

        if not target_transition:
            return Response({
                'status': 'error',
                'message': f'No valid transition for Action: {action} on Stage: {application.current_stage.name if application.current_stage else "None"}'
            }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            if action in ('PAY', 'FORCE_PAY'):
                from decimal import Decimal
                from django.db.models import Q
                from models.transactional.wallet.models import WalletBalance
                from models.transactional.wallet.wallet_service import debit_wallet_balance

                total_import_fee = Decimal('0.00')
                total_add_ed = Decimal('0.00')
                total_edu_cess = Decimal('0.00')

                line_items = list(getattr(application, 'line_items', []).all() if hasattr(application, 'line_items') else [])
                if line_items:
                    for item in line_items:
                        cases = Decimal(str(getattr(item, 'cases', 0) or getattr(item, 'no_of_cases', 0) or getattr(item, 'quantity', 0) or 0))
                        import_fee_rate = Decimal(str(getattr(item, 'import_pass_fee_per_case', 0) or getattr(item, 'import_pass_fee', 0) or 0))
                        add_ed_rate = Decimal(str(getattr(item, 'additional_ed_per_case', 0) or getattr(item, 'additional_ed', 0) or 0))
                        cess_rate = Decimal(str(getattr(item, 'education_cess_per_case', 0) or getattr(item, 'education_cess', 0) or 0))

                        total_import_fee += (import_fee_rate * cases)
                        total_add_ed += (add_ed_rate * cases)
                        total_edu_cess += (cess_rate * cases)

                if total_import_fee == 0 and total_add_ed == 0 and total_edu_cess == 0:
                    details = getattr(application, 'permit_wise_details', []) or []
                    if isinstance(details, list):
                        for p in details:
                            if isinstance(p, dict):
                                items = p.get('line_items') or p.get('items') or []
                                for item in items:
                                    if isinstance(item, dict):
                                        cases = Decimal(str(item.get('cases', 0) or 0))
                                        import_fee = Decimal(str(item.get('total_import') or item.get('totalImport') or (item.get('import_pass_fee_per_case', 0) * cases)))
                                        add_ed = Decimal(str(item.get('total_additional_ed') or item.get('totalAddEd') or (item.get('additional_ed_per_case', 0) * cases)))
                                        cess = Decimal(str(item.get('total_education_cess') or item.get('cess') or 0))

                                        total_import_fee += import_fee
                                        total_add_ed += add_ed
                                        total_edu_cess += cess

                excise_amount = (total_import_fee + total_add_ed).quantize(Decimal('0.01'))
                cess_amount = total_edu_cess.quantize(Decimal('0.01'))

                user_obj = getattr(application, 'applicant', None) or request.user
                username = str(getattr(user_obj, 'username', '') or '').strip()

                candidates = [username]
                from models.masters.license.models import License
                for lic in License.objects.filter(applicant=user_obj, is_active=True):
                    if lic.license_id:
                        candidates.append(str(lic.license_id).strip())

                wallet_filter = Q(user_id__iexact=username) | Q(licensee_id__in=candidates)
                if hasattr(WalletBalance, 'applicant'):
                    wallet_filter |= Q(applicant=user_obj)

                excise_wallet = WalletBalance.objects.filter(
                    wallet_filter,
                    wallet_type__code__iexact='excise'
                ).order_by('-current_balance', 'wallet_balance_id').first()

                if not excise_wallet and excise_amount > 0:
                    return Response({'status': 'error', 'message': f'Excise Wallet not found for user {username}.'}, status=status.HTTP_400_BAD_REQUEST)

                if excise_wallet and Decimal(str(excise_wallet.current_balance or 0)) < excise_amount:
                    return Response({
                        'status': 'error',
                        'message': f'Insufficient Excise Wallet balance (Required: ₹{excise_amount}, Available: ₹{excise_wallet.current_balance}).'
                    }, status=status.HTTP_400_BAD_REQUEST)

                cess_wallet = None
                if cess_amount > 0:
                    cess_wallet = WalletBalance.objects.filter(
                        wallet_filter,
                        wallet_type__code__iexact='education_cess'
                    ).order_by('-current_balance', 'wallet_balance_id').first()

                    if not cess_wallet:
                        return Response({'status': 'error', 'message': f'Education Cess Wallet not found for user {username}.'}, status=status.HTTP_400_BAD_REQUEST)

                    if Decimal(str(cess_wallet.current_balance or 0)) < cess_amount:
                        return Response({
                            'status': 'error',
                            'message': f'Insufficient Education Cess Wallet balance (Required: ₹{cess_amount}, Available: ₹{cess_wallet.current_balance}).'
                        }, status=status.HTTP_400_BAD_REQUEST)

                import uuid
                ref_no_str = application.reference_no

                if excise_wallet and excise_amount > 0:
                    if total_import_fee > 0 and total_add_ed > 0:
                        ed_txn_id = f"PAY-EXCISE-ED-{ref_no_str}-{uuid.uuid4().hex[:6].upper()}"
                        debit_wallet_balance(
                            transaction_id=ed_txn_id,
                            licensee_id=excise_wallet.licensee_id,
                            wallet_type="excise",
                            head_of_account=excise_wallet.head_of_account,
                            amount=total_import_fee,
                            user_id=username,
                            remarks=f"IMFL Requisition Excise Duty (Import Pass Fee ₹{total_import_fee}) for Ref #{ref_no_str}",
                            reference_no=ref_no_str,
                            source_module="imfl_permit_requisition_excise",
                            transaction_type="payment"
                        )
                        add_txn_id = f"PAY-EXCISE-ADD-{ref_no_str}-{uuid.uuid4().hex[:6].upper()}"
                        debit_wallet_balance(
                            transaction_id=add_txn_id,
                            licensee_id=excise_wallet.licensee_id,
                            wallet_type="additional_excise",
                            head_of_account=excise_wallet.head_of_account,
                            amount=total_add_ed,
                            user_id=username,
                            remarks=f"IMFL Requisition Additional Excise Duty (Add. ED ₹{total_add_ed}) for Ref #{ref_no_str}",
                            reference_no=ref_no_str,
                            source_module="imfl_permit_requisition_additional_ed",
                            transaction_type="payment"
                        )
                    else:
                        excise_txn_id = f"PAY-EXCISE-{ref_no_str}-{uuid.uuid4().hex[:6].upper()}"
                        debit_wallet_balance(
                            transaction_id=excise_txn_id,
                            licensee_id=excise_wallet.licensee_id,
                            wallet_type="excise",
                            head_of_account=excise_wallet.head_of_account,
                            amount=excise_amount,
                            user_id=username,
                            remarks=f"IMFL Requisition Excise Duty Fee Payment for Ref #{ref_no_str}",
                            reference_no=ref_no_str,
                            source_module="imfl_permit_requisition_excise",
                            transaction_type="payment"
                        )

                if cess_wallet and cess_amount > 0:
                    cess_txn_id = f"PAY-CESS-{ref_no_str}-{uuid.uuid4().hex[:6].upper()}"
                    debit_wallet_balance(
                        transaction_id=cess_txn_id,
                        licensee_id=cess_wallet.licensee_id,
                        wallet_type="education_cess",
                        head_of_account=cess_wallet.head_of_account,
                        amount=cess_amount,
                        user_id=username,
                        remarks=f"IMFL Requisition Education Duty Payment (Education Cess ₹{cess_amount}) for Ref #{ref_no_str}",
                        reference_no=ref_no_str,
                        source_module="imfl_permit_requisition_education_cess",
                        transaction_type="payment"
                    )

            WorkflowService.advance_stage(
                application=application,
                user=request.user,
                target_stage=target_transition.to_stage,
                context={'action': action},
                remarks=remarks or f"Action: {action}"
            )

            # Sync status/officer remarks
            application.status = target_transition.to_stage.name
            if action in ('PAY', 'FORCE_PAY') and hasattr(application, 'is_excise_duty_fee_paid'):
                application.is_excise_duty_fee_paid = True
            if remarks and hasattr(application, 'officer_remarks'):
                application.officer_remarks = remarks

            if action == 'APPROVE' and target_transition.to_stage.is_final and hasattr(application, 'submitted_at'):
                application.submitted_at = timezone.now()

            application.save()
            invalidate_dashboard_counts_cache()

            is_approved_stage = (
                target_transition.to_stage.id in (151, 165) or
                getattr(target_transition.to_stage, 'is_final', False) or
                str(getattr(target_transition.to_stage, 'name', '')).lower() in ('approved', 'approved by commissioner')
            )

            if is_approved_stage:
                if isinstance(application, DistributorPermitApplication):
                    _schedule_imfl_revalidation_activation(application, timezone.now())
                elif isinstance(application, IMFLRevalidation):
                    from datetime import timedelta
                    delay_seconds = _resolve_imfl_revalidation_activation_delay_seconds()
                    new_valid_until = timezone.now() + timedelta(seconds=delay_seconds)

                    application.valid_up_to = new_valid_until
                    application.save(update_fields=['valid_up_to'])

                    if application.distributor_permit:
                        application.distributor_permit.valid_up_to = new_valid_until
                        application.distributor_permit.save(update_fields=['valid_up_to', 'updated_at'])

                        existing_pending = IMFLRevalidationActivationSchedule.objects.filter(
                            distributor_permit=application.distributor_permit,
                            status=IMFLRevalidationActivationSchedule.STATUS_PENDING
                        ).order_by('-id').first()

                        if existing_pending:
                            existing_pending.approval_date = timezone.now()
                            existing_pending.activation_due_at = new_valid_until
                            existing_pending.activated_at = None
                            existing_pending.notes = f"Revalidation cycle schedule for {application.reference_no}"
                            existing_pending.save()
                        else:
                            IMFLRevalidationActivationSchedule.objects.create(
                                distributor_permit=application.distributor_permit,
                                distributor_permit_ref_no=str(application.distributor_permit.reference_no),
                                approval_date=timezone.now(),
                                activation_due_at=new_valid_until,
                                activated_at=None,
                                status=IMFLRevalidationActivationSchedule.STATUS_PENDING,
                                notes=f"Revalidation cycle schedule for {application.reference_no}"
                            )

        return Response({
            'status': 'success',
            'message': f'Action {action} performed successfully. Stage updated to {target_transition.to_stage.name}.',
            'current_stage': target_transition.to_stage.name
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
        if cfg and cfg.delay_value:
            val = int(cfg.delay_value)
            unit = (cfg.delay_unit or 'day').lower()
            if unit == 'day':
                return val
            elif unit == 'month':
                return val * 30
            elif unit == 'year':
                return val * 365
            elif unit == 'week':
                return val * 7
            return val
    except Exception:
        pass
    return default_days


def _schedule_imfl_revalidation_activation(application, approved_at=None):
    from datetime import timedelta
    from django.utils import timezone
    from .models import IMFLRevalidationActivationSchedule

    approved_at = approved_at or timezone.now()
    delay_seconds = _resolve_imfl_revalidation_activation_delay_seconds()
    valid_until = approved_at + timedelta(seconds=delay_seconds)

    application.approval_date = approved_at
    application.valid_up_to = valid_until
    application.save(update_fields=['approval_date', 'valid_up_to', 'updated_at'])

    existing_pending = IMFLRevalidationActivationSchedule.objects.filter(
        distributor_permit=application,
        status=IMFLRevalidationActivationSchedule.STATUS_PENDING
    ).order_by('-id').first()

    if existing_pending:
        existing_pending.approval_date = approved_at
        existing_pending.activation_due_at = valid_until
        existing_pending.activated_at = None
        existing_pending.notes = f"Initial revalidation schedule for {application.reference_no}"
        existing_pending.save()
    else:
        IMFLRevalidationActivationSchedule.objects.create(
            distributor_permit=application,
            distributor_permit_ref_no=str(application.reference_no),
            approval_date=approved_at,
            activation_due_at=valid_until,
            activated_at=None,
            status=IMFLRevalidationActivationSchedule.STATUS_PENDING,
            notes=f"Initial revalidation schedule for {application.reference_no}"
        )


def _process_due_imfl_activation_schedules():
    from django.utils import timezone
    from .models import IMFLRevalidationActivationSchedule, IMFLCancellation

    now = timezone.now()
    schedules = IMFLRevalidationActivationSchedule.objects.filter(
        status=IMFLRevalidationActivationSchedule.STATUS_PENDING,
        activation_due_at__lte=now
    ).select_related('distributor_permit', 'distributor_permit__applicant')

    for schedule in schedules:
        dp = schedule.distributor_permit
        if not dp:
            continue

        # Skip if permit is cancelled
        has_cancellation = IMFLCancellation.objects.filter(
            distributor_permit=dp
        ).filter(status__icontains='approved').exists()

        if has_cancellation:
            continue

        schedule.status = IMFLRevalidationActivationSchedule.STATUS_PROCESSED
        schedule.activated_at = schedule.activation_due_at or now
        schedule.save(update_fields=['status', 'activated_at', 'updated_at'])


from rest_framework import viewsets
from rest_framework.decorators import action
from .models import IMFLRevalidation, IMFLCancellation, IMFLRevalidationActivationSchedule, IMFLArrival
from .serializers import (
    IMFLRevalidationSerializer,
    IMFLCancellationSerializer,
    IMFLRevalidationActivationScheduleSerializer,
    IMFLArrivalSerializer,
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
    lookup_value_regex = '.+'

    def get_queryset(self):
        _process_due_imfl_activation_schedules()
        qs = IMFLRevalidation.objects.select_related('distributor_permit', 'applicant', 'current_stage').all()
        return scope_permit_queryset(qs, self.request.user)

    def list(self, request, *args, **kwargs):
        _process_due_imfl_activation_schedules()
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            data = list(serializer.data)
        else:
            serializer = self.get_serializer(queryset, many=True)
            data = list(serializer.data)

        # Query all schedules ordered by newest first (-id) to find the LATEST schedule state per permit
        if _is_officer_user(request.user):
            all_schedules = IMFLRevalidationActivationSchedule.objects.all().select_related('distributor_permit', 'distributor_permit__applicant').order_by('-id')
        else:
            all_schedules = IMFLRevalidationActivationSchedule.objects.filter(
                distributor_permit__applicant=request.user
            ).select_related('distributor_permit', 'distributor_permit__applicant').order_by('-id')
            if not all_schedules.exists():
                all_schedules = IMFLRevalidationActivationSchedule.objects.all().select_related('distributor_permit', 'distributor_permit__applicant').order_by('-id')

        latest_schedules_by_ref = {}
        for sched in all_schedules:
            ref_no = str(sched.distributor_permit_ref_no)
            if ref_no not in latest_schedules_by_ref:
                latest_schedules_by_ref[ref_no] = sched

        pending_permit_refs = set()
        for item in data:
            status_str = str(item.get('status') or '').upper()
            stage_dict = item.get('current_stage') or {}
            is_final = False
            if isinstance(stage_dict, dict):
                is_final = bool(stage_dict.get('is_final'))

            # Only mark permit as "pending" if it has an unapproved revalidation in progress
            if not is_final and 'APPROVED' not in status_str:
                dp_id = item.get('distributor_permit') or item.get('distributor_permit_id')
                if isinstance(dp_id, dict):
                    ref = dp_id.get('reference_no') or dp_id.get('referenceNo')
                    if ref:
                        pending_permit_refs.add(str(ref))
                    dp_pk = dp_id.get('id')
                    if dp_pk:
                        pending_permit_refs.add(str(dp_pk))
                elif dp_id:
                    pending_permit_refs.add(str(dp_id))

                dp_ref = item.get('distributor_permit_ref_no') or item.get('distributor_permit_ref')
                if dp_ref:
                    pending_permit_refs.add(str(dp_ref))

        for ref_no, sched in latest_schedules_by_ref.items():
            # Check if the latest schedule entry is actually PROCESSED and has activated_at set
            if sched.status != IMFLRevalidationActivationSchedule.STATUS_PROCESSED or not sched.activated_at:
                continue

            dp_pk = str(sched.distributor_permit_id) if sched.distributor_permit_id else None

            # Skip if there is an active unapproved revalidation application currently in progress
            if ref_no in pending_permit_refs or (dp_pk and dp_pk in pending_permit_refs):
                continue

            dp = sched.distributor_permit
            supplier_name = getattr(dp, 'supplier_company_name', 'N/A') if dp else 'N/A'
            applicant_name = getattr(getattr(dp, 'applicant', None), 'full_name', str(getattr(dp, 'applicant', ''))) if dp else str(request.user)
            dp_pdetails = getattr(dp, 'permit_wise_details', []) if dp else []
            data.append({
                'reference_no': ref_no,
                'referenceNo': ref_no,
                'applicationId': ref_no,
                'distributor_permit': ref_no,
                'distributor_permit_id': ref_no,
                'revalidated_permit_number': ref_no,
                'revalidatedPermitNumber': ref_no,
                'applicant_name': applicant_name,
                'applicantName': applicant_name,
                'supplier_company_name': supplier_name,
                'supplierName': supplier_name,
                'status': 'Revalidation Activated',
                'current_stage': {'name': 'Permit Expired - Ready for Revalidation'},
                'currentStage': 'Permit Expired - Ready for Revalidation',
                'is_activated_schedule': True,
                'can_submit_application': True,
                'permit_wise_details': dp_pdetails,
                'permitWiseDetails': dp_pdetails,
                'created_at': sched.activated_at or sched.updated_at,
                'submitted_at': sched.activated_at or sched.updated_at,
            })

        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)

    def perform_create(self, serializer):
        from django.utils import timezone
        from auth.workflow.models import Workflow, WorkflowStage
        from auth.workflow.constants import WORKFLOW_IDS

        ref_no = DistributorPermitApplication.generate_reference_no(app_type='revalidation')
        workflow_id = WORKFLOW_IDS.get('IMFL_REVALIDATION', 16)
        workflow = Workflow.objects.filter(id=workflow_id).first()
        initial_stage = WorkflowStage.objects.filter(id=160).first() or (workflow.stages.filter(is_initial=True).first() if workflow else None)
        status_name = initial_stage.name if initial_stage else 'Forwarded To Commissioner'

        target_permit_no = self.request.data.get('revalidated_permit_number') or self.request.data.get('original_permit_no') or self.request.data.get('revalidatedPermitNumber') or ''
        p_details = self.request.data.get('permit_wise_details') or self.request.data.get('permitWiseDetails') or []

        distributor_permit = serializer.validated_data.get('distributor_permit')
        if not distributor_permit:
            dp_ref = self.request.data.get('distributor_permit') or self.request.data.get('distributorPermit')
            if dp_ref:
                distributor_permit = DistributorPermitApplication.objects.filter(reference_no=str(dp_ref)).first()

        if distributor_permit and not p_details:
            app_pdetails = getattr(distributor_permit, 'permit_wise_details', []) or []
            if target_permit_no:
                matched = [p for p in app_pdetails if str(p.get('permit_number', '')).lower() == str(target_permit_no).lower()]
                p_details = matched if matched else app_pdetails
            else:
                p_details = app_pdetails

        serializer.save(
            reference_no=ref_no,
            applicant=self.request.user,
            distributor_permit=distributor_permit,
            submitted_at=timezone.now(),
            workflow=workflow,
            current_stage=initial_stage,
            status=status_name,
            revalidated_permit_number=target_permit_no or (distributor_permit.reference_no if distributor_permit else ''),
            permit_wise_details=p_details
        )
        invalidate_dashboard_counts_cache()

        # Debit Rs.1000 revalidation fee per permit from Excise wallet
        try:
            from decimal import Decimal
            permit_numbers_in_details = list({
                str(p.get('permit_number', '')).strip()
                for p in p_details
                if isinstance(p, dict) and p.get('permit_number')
            }) if p_details else []
            num_permits = len(permit_numbers_in_details) or 1
            revalidation_fee = Decimal('1000.00') * num_permits

            user_obj = self.request.user
            dist_applicant = getattr(distributor_permit, 'applicant', None) or user_obj
            username = str(getattr(user_obj, 'username', '') or getattr(dist_applicant, 'username', '') or '').strip()

            raw_licensee_id = str(
                getattr(distributor_permit, 'licensee_id', None) or
                getattr(dist_applicant, 'licensee_id', None) or
                getattr(dist_applicant, 'username', None) or
                username
            ).strip()

            from django.db.models import Q
            from models.transactional.wallet.models import WalletBalance
            wb = WalletBalance.objects.filter(
                Q(licensee_id__iexact=raw_licensee_id) |
                Q(user_id__iexact=raw_licensee_id) |
                Q(user_id__iexact=username)
            ).first()

            licensee_id = str(wb.licensee_id).strip() if (wb and wb.licensee_id) else raw_licensee_id
            from models.transactional.wallet.wallet_service import debit_wallet_balance

            debit_wallet_balance(
                transaction_id=f'PAY-EXCISE-REVAL-FEE-{ref_no}',
                licensee_id=licensee_id,
                wallet_type='excise',
                head_of_account='0039-00-105-45-01',
                amount=revalidation_fee,
                user_id=username,
                source_module='imfl_permit_revalidation_fee',
                reference_no=ref_no,
                remarks=f'IMFL Permit Revalidation Fee (Rs. {revalidation_fee} for {num_permits} permit(s)) for Ref #{ref_no}'
            )
        except Exception as err:
            logging.getLogger(__name__).error(
                "IMFL revalidation wallet fee FAILED for %s: %s\n%s",
                ref_no, err, traceback.format_exc()
            )


    @action(detail=True, methods=['post'], url_path='perform_action')
    def perform_action(self, request, reference_no=None):
        return DistributorPermitPerformActionView().post(request, reference_no=reference_no)

    @action(detail=True, methods=['post'], url_path='perform-action')
    def perform_action_hyphen(self, request, reference_no=None):
        return DistributorPermitPerformActionView().post(request, reference_no=reference_no)


class IMFLCancellationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = IMFLCancellationSerializer
    lookup_field = 'reference_no'
    lookup_value_regex = '.+'

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

        target_permit_no = self.request.data.get('cancelled_permit_number') or self.request.data.get('cancelledPermitNumber') or ''
        p_details = self.request.data.get('permit_wise_details') or self.request.data.get('permitWiseDetails') or []

        distributor_permit = serializer.validated_data.get('distributor_permit')
        if distributor_permit and not p_details:
            app_pdetails = getattr(distributor_permit, 'permit_wise_details', []) or []
            if target_permit_no:
                matched = [p for p in app_pdetails if str(p.get('permit_number', '')).lower() == str(target_permit_no).lower()]
                p_details = matched if matched else app_pdetails
            else:
                p_details = app_pdetails

        cancellation_obj = serializer.save(
            reference_no=ref_no,
            applicant=self.request.user,
            cancelled_permit_number=target_permit_no,
            permit_wise_details=p_details,
            submitted_at=timezone.now(),
            workflow=workflow,
            current_stage=initial_stage,
            status=status_name
        )

        try:
            total_import_fee = Decimal('0.00')
            total_add_ed = Decimal('0.00')
            total_edu_cess = Decimal('0.00')

            line_items = []
            if distributor_permit:
                app_line_items = list(getattr(distributor_permit, 'line_items', []).all() if hasattr(distributor_permit, 'line_items') else [])
                if target_permit_no and app_line_items:
                    matched = [item for item in app_line_items if str(getattr(item, 'permit_number', '')).lower() == str(target_permit_no).lower()]
                    if matched:
                        line_items = matched

            if p_details:
                for p in p_details:
                    if isinstance(p, dict):
                        p_cases = Decimal(str(p.get('total_cases', 0) or p.get('cases', 0) or 0))
                        p_import = Decimal(str(p.get('total_import_fee', 0) or p.get('total_import', 0) or 0))
                        p_add_ed = Decimal(str(p.get('total_additional_ed', 0) or 0))
                        p_cess = Decimal(str(p.get('total_education_cess', 0) or 0))

                        items = p.get('line_items') or p.get('items') or []
                        if items:
                            for item in items:
                                if isinstance(item, dict):
                                    cases = Decimal(str(item.get('cases', 0) or p_cases or 0))
                                    imp_fee = Decimal(str(item.get('total_import') or item.get('totalImport') or (Decimal(str(item.get('import_pass_fee_per_case', 1400) or 1400)) * cases)))
                                    add_ed = Decimal(str(item.get('total_additional_ed') or item.get('totalAddEd') or (Decimal(str(item.get('additional_ed_per_case', 350) or 350)) * cases)))
                                    cess = Decimal(str(item.get('total_education_cess') or item.get('cess') or (Decimal(str(item.get('education_cess_per_case', 60) or 60)) * cases)))

                                    total_import_fee += imp_fee
                                    total_add_ed += add_ed
                                    total_edu_cess += cess
                        else:
                            total_import_fee += p_import if p_import > 0 else (Decimal('1400.00') * p_cases)
                            total_add_ed += p_add_ed
                            total_edu_cess += p_cess if p_cess > 0 else (Decimal('60.00') * p_cases)

            if total_import_fee == 0 and line_items:
                for item in line_items:
                    imp_rate = Decimal(str(getattr(item, 'import_pass_fee_per_case', 1400) or 1400))
                    add_rate = Decimal(str(getattr(item, 'additional_ed_per_case', 350) or 350))
                    cess_rate = Decimal(str(getattr(item, 'education_cess_per_case', 60) or 60))
                    cases = Decimal('1.00')
                    total_import_fee += (imp_rate * cases)
                    total_add_ed += (add_rate * cases)
                    total_edu_cess += (cess_rate * cases)

            # Cancellation fee = Rs.1000 per permit being cancelled
            permit_numbers_in_details = list({
                str(p.get('permit_number', '')).strip()
                for p in p_details
                if isinstance(p, dict) and p.get('permit_number')
            }) if p_details else []
            num_permits = len(permit_numbers_in_details) or 1
            cancellation_fee = Decimal('1000.00') * num_permits

            user_obj = self.request.user
            dist_applicant = getattr(distributor_permit, 'applicant', None) or user_obj
            username = str(getattr(user_obj, 'username', '') or getattr(dist_applicant, 'username', '') or '').strip()

            raw_licensee_id = str(
                getattr(distributor_permit, 'licensee_id', None) or
                getattr(dist_applicant, 'licensee_id', None) or
                getattr(dist_applicant, 'username', None) or
                username
            ).strip()

            from django.db.models import Q
            from models.transactional.wallet.models import WalletBalance
            wb = WalletBalance.objects.filter(
                Q(licensee_id__iexact=raw_licensee_id) |
                Q(user_id__iexact=raw_licensee_id) |
                Q(user_id__iexact=username)
            ).first()

            licensee_id = str(wb.licensee_id).strip() if (wb and wb.licensee_id) else raw_licensee_id
            from models.transactional.wallet.wallet_service import debit_wallet_balance, credit_wallet_balance

            # 1. Debit Cancellation Processing Fee (Rs.1000 per permit) from Excise wallet
            debit_wallet_balance(
                transaction_id=f"PAY-EXCISE-CAN-FEE-{ref_no}",
                licensee_id=licensee_id,
                wallet_type="excise",
                head_of_account="0039-00-105-45-01",
                amount=cancellation_fee,
                user_id=username,
                source_module="imfl_permit_cancellation_fee",
                reference_no=ref_no,
                remarks=f"IMFL Cancellation Processing Fee (Rs. {cancellation_fee} for {num_permits} permit(s)) for Ref #{ref_no}"
            )

            # 2. Credit Excise Duty Refund (Import Pass Fee) — Excise wallet
            if total_import_fee > 0:
                credit_wallet_balance(
                    transaction_id=f"PAY-EXCISE-ED-REFUND-{ref_no}",
                    licensee_id=licensee_id,
                    wallet_type="excise",
                    head_of_account="0039-00-105-45-01",
                    amount=total_import_fee,
                    user_id=username,
                    source_module="imfl_permit_cancellation_excise",
                    transaction_type="refund",
                    reference_no=ref_no,
                    remarks=f"IMFL Cancellation Excise Duty Refund (Import Pass Fee Rs. {total_import_fee}) for Ref #{ref_no}"
                )

            # 3. Credit Additional Excise Duty Refund — stored as additional_excise (uses excise wallet balance row)
            if total_add_ed > 0:
                credit_wallet_balance(
                    transaction_id=f"PAY-EXCISE-ADD-REFUND-{ref_no}",
                    licensee_id=licensee_id,
                    wallet_type="additional_excise",
                    head_of_account="0039-00-105-45-01",
                    amount=total_add_ed,
                    user_id=username,
                    source_module="imfl_permit_cancellation_additional_ed",
                    transaction_type="refund",
                    reference_no=ref_no,
                    remarks=f"IMFL Cancellation Additional Excise Duty Refund (Add. ED Rs. {total_add_ed}) for Ref #{ref_no}"
                )

            # 4. Credit Education Cess Refund — Education Cess wallet
            if total_edu_cess > 0:
                credit_wallet_balance(
                    transaction_id=f"PAY-CESS-REFUND-{ref_no}",
                    licensee_id=licensee_id,
                    wallet_type="education_cess",
                    head_of_account="0045-00-112-45-03",
                    amount=total_edu_cess,
                    user_id=username,
                    source_module="imfl_permit_cancellation_education_cess",
                    transaction_type="refund",
                    reference_no=ref_no,
                    remarks=f"IMFL Cancellation Education Cess Refund (Rs. {total_edu_cess}) for Ref #{ref_no}"
                )
        except Exception as err:
            import logging
            import traceback
            logging.getLogger(__name__).error(
                "IMFL cancellation wallet refund FAILED for %s: %s\n%s",
                ref_no, err, traceback.format_exc()
            )


    @action(detail=True, methods=['post'], url_path='perform_action')
    def perform_action(self, request, reference_no=None):
        handler = DistributorPermitPerformActionView()
        return handler.post(request, reference_no=reference_no)

    @action(detail=True, methods=['post'], url_path='perform-action')
    def perform_action_hyphen(self, request, reference_no=None):
        handler = DistributorPermitPerformActionView()
        return handler.post(request, reference_no=reference_no)


class IMFLArrivalViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = IMFLArrivalSerializer

    def get_queryset(self):
        user = self.request.user
        qs = IMFLArrival.objects.select_related('distributor_permit', 'arrived_by').all()

        permit_no = self.request.query_params.get('permit_number') or self.request.query_params.get('permitNumber')
        dist_permit = self.request.query_params.get('distributor_permit') or self.request.query_params.get('distributorPermit')

        if permit_no:
            qs = qs.filter(permit_number__iexact=str(permit_no).strip())
        if dist_permit:
            qs = qs.filter(
                models.Q(distributor_permit__reference_no__iexact=str(dist_permit).strip()) |
                models.Q(distributor_permit_id=str(dist_permit).strip())
            )

        if not _is_officer_user(user):
            qs = qs.filter(
                models.Q(arrived_by=user) |
                models.Q(distributor_permit__applicant=user)
            )
        return qs

    def perform_create(self, serializer):
        from django.utils import timezone
        dp_id = self.request.data.get('distributor_permit') or self.request.data.get('distributorPermit') or self.request.data.get('distributor_permit_id')
        dp = None
        if dp_id:
            if isinstance(dp_id, dict):
                dp_ref = dp_id.get('reference_no') or dp_id.get('referenceNo') or dp_id.get('id')
                dp = DistributorPermitApplication.objects.filter(reference_no=str(dp_ref)).first()
            elif isinstance(dp_id, int):
                dp = DistributorPermitApplication.objects.filter(id=dp_id).first()
            else:
                dp = DistributorPermitApplication.objects.filter(reference_no=str(dp_id)).first()

        serializer.save(
            distributor_permit=dp or serializer.validated_data.get('distributor_permit'),
            arrived_by=self.request.user,
            arrived_at=timezone.now()
        )

    def perform_create(self, serializer):
        from django.utils import timezone
        from auth.workflow.models import Workflow, WorkflowStage
        from auth.workflow.constants import WORKFLOW_IDS

        ref_no = DistributorPermitApplication.generate_reference_no(app_type='revalidation')
        workflow_id = WORKFLOW_IDS.get('IMFL_REVALIDATION', 16)
        workflow = Workflow.objects.filter(id=workflow_id).first()
        initial_stage = WorkflowStage.objects.filter(id=160).first() or (workflow.stages.filter(is_initial=True).first() if workflow else None)
        status_name = initial_stage.name if initial_stage else 'Forwarded To Commissioner'

        target_permit_no = self.request.data.get('revalidated_permit_number') or self.request.data.get('original_permit_no') or self.request.data.get('revalidatedPermitNumber') or ''
        p_details = self.request.data.get('permit_wise_details') or self.request.data.get('permitWiseDetails') or []

        distributor_permit = serializer.validated_data.get('distributor_permit')
        if not distributor_permit:
            dp_ref = self.request.data.get('distributor_permit') or self.request.data.get('distributorPermit')
            if dp_ref:
                distributor_permit = DistributorPermitApplication.objects.filter(reference_no=str(dp_ref)).first()

        if distributor_permit and not p_details:
            app_pdetails = getattr(distributor_permit, 'permit_wise_details', []) or []
            if target_permit_no:
                matched = [p for p in app_pdetails if str(p.get('permit_number', '')).lower() == str(target_permit_no).lower()]
                p_details = matched if matched else app_pdetails
            else:
                p_details = app_pdetails

        serializer.save(
            reference_no=ref_no,
            applicant=self.request.user,
            distributor_permit=distributor_permit,
            submitted_at=timezone.now(),
            workflow=workflow,
            current_stage=initial_stage,
            status=status_name,
            revalidated_permit_number=target_permit_no or (distributor_permit.reference_no if distributor_permit else ''),
            permit_wise_details=p_details
        )
        invalidate_dashboard_counts_cache()

    @action(detail=True, methods=['post'], url_path='perform_action')
    def perform_action(self, request, reference_no=None):
        return DistributorPermitPerformActionView().post(request, reference_no=reference_no)

    @action(detail=True, methods=['post'], url_path='perform-action')
    def perform_action_hyphen(self, request, reference_no=None):
        return DistributorPermitPerformActionView().post(request, reference_no=reference_no)

class IMFLArrivalViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = IMFLArrivalSerializer

    def get_queryset(self):
        user = self.request.user
        qs = IMFLArrival.objects.select_related('distributor_permit', 'arrived_by').all()

        permit_no = self.request.query_params.get('permit_number') or self.request.query_params.get('permitNumber')
        dist_permit = self.request.query_params.get('distributor_permit') or self.request.query_params.get('distributorPermit')

        if permit_no:
            qs = qs.filter(permit_number__iexact=str(permit_no).strip())
        if dist_permit:
            qs = qs.filter(
                Q(distributor_permit__reference_no__iexact=str(dist_permit).strip()) |
                Q(distributor_permit_id=str(dist_permit).strip())
            )

        if not _is_officer_user(user):
            qs = qs.filter(
                Q(arrived_by=user) |
                Q(distributor_permit__applicant=user)
            )
        return qs

    def perform_create(self, serializer):
        from django.utils import timezone
        dp_id = self.request.data.get('distributor_permit') or self.request.data.get('distributorPermit') or self.request.data.get('distributor_permit_id')
        dp = None
        if dp_id:
            if isinstance(dp_id, dict):
                dp_ref = dp_id.get('reference_no') or dp_id.get('referenceNo') or dp_id.get('id')
                dp = DistributorPermitApplication.objects.filter(reference_no=str(dp_ref)).first()
            elif isinstance(dp_id, int):
                dp = DistributorPermitApplication.objects.filter(id=dp_id).first()
            else:
                dp = DistributorPermitApplication.objects.filter(reference_no=str(dp_id)).first()

        serializer.save(
            distributor_permit=dp or serializer.validated_data.get('distributor_permit'),
            arrived_by=self.request.user,
            arrived_at=timezone.now()
        )


class IMFLCasesProcessedViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = IMFLCasesProcessedSerializer

    def get_queryset(self):
        user = self.request.user
        qs = IMFLCasesProcessed.objects.select_related('distributor_permit', 'submitted_by', 'oic_officer').all()

        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status__iexact=str(status_param).strip())

        if _is_officer_user(user):
            from auth.user.models import OICOfficerAssignment
            assignment = OICOfficerAssignment.objects.filter(officer=user).first()
            if assignment and getattr(assignment, 'distributor_user', None):
                qs = qs.filter(
                    Q(oic_officer=user) |
                    Q(submitted_by=assignment.distributor_user) |
                    Q(distributor_permit__applicant=assignment.distributor_user)
                )
            else:
                qs = qs.filter(Q(oic_officer=user) | Q(oic_officer__isnull=True))
        else:
            qs = qs.filter(Q(submitted_by=user) | Q(distributor_permit__applicant=user))

        return qs

    def perform_create(self, serializer):
        from django.utils import timezone
        user = self.request.user
        dp_id = self.request.data.get('distributor_permit') or self.request.data.get('distributorPermit')
        dp = None
        if dp_id:
            if isinstance(dp_id, dict):
                dp_ref = dp_id.get('reference_no') or dp_id.get('referenceNo') or dp_id.get('id')
                dp = DistributorPermitApplication.objects.filter(reference_no=str(dp_ref)).first()
            elif isinstance(dp_id, int):
                dp = DistributorPermitApplication.objects.filter(id=dp_id).first()
            else:
                dp = DistributorPermitApplication.objects.filter(reference_no=str(dp_id)).first()

        oic_user = None
        from auth.user.models import OICOfficerAssignment
        assignment = OICOfficerAssignment.objects.filter(distributor_user=user, assignment_type='distributor').first()
        if assignment:
            oic_user = assignment.officer

        serializer.save(
            distributor_permit=dp or serializer.validated_data.get('distributor_permit'),
            submitted_by=user,
            oic_officer=oic_user,
            status='under_review',
            submitted_at=timezone.now()
        )

    @action(detail=True, methods=['post'], url_path='action')
    def action(self, request, pk=None):
        from django.utils import timezone
        instance = self.get_object()
        user = request.user
        action_val = str(request.data.get('action') or '').strip().lower()
        remarks = str(request.data.get('remarks') or '').strip()

        if action_val not in ('approve', 'approved', 'reject', 'rejected'):
            return Response({'detail': 'Invalid action. Must be approve or reject.'}, status=status.HTTP_400_BAD_REQUEST)

        if action_val in ('approve', 'approved'):
            instance.status = 'approved'
            instance.reviewed_at = timezone.now()
            instance.officer_remarks = remarks
            instance.save()

            # Create or update corresponding record in imfl_cases (IMFLArrival) table
            IMFLArrival.objects.get_or_create(
                distributor_permit=instance.distributor_permit,
                permit_number=instance.permit_number,
                vehicle_number=instance.vehicle_number,
                brand_name=instance.brand_name,
                defaults={
                    'size_ml': instance.size_ml,
                    'expected_cases': instance.expected_cases,
                    'arrived_cases': instance.arrived_cases,
                    'remarks': instance.remarks,
                    'arrived_by': instance.submitted_by,
                    'arrived_at': timezone.now(),
                    'status': 'Approved',
                }
            )
            return Response({'message': 'Stock arrival approved successfully and stored in IMFL cases register.', 'status': 'approved'})

        elif action_val in ('reject', 'rejected'):
            instance.status = 'rejected'
            instance.reviewed_at = timezone.now()
            instance.officer_remarks = remarks
            instance.save()
            return Response({'message': 'Stock arrival rejected.', 'status': 'rejected'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def distributor_permit_wallet_balances(request):
    from django.db.models import Q
    from models.transactional.wallet.models import WalletBalance
    from models.masters.license.models import License
    from models.transactional.wallet.wallet_initializer import initialize_wallet_balances_for_license

    user = request.user
    user_id = str(getattr(user, 'username', '') or '').strip()

    # Expand candidate license IDs for this user
    candidates = [user_id]
    user_licenses = list(License.objects.filter(applicant=user, is_active=True))
    for lic in user_licenses:
        if lic.license_id:
            candidates.append(str(lic.license_id).strip())
            # Initialize wallets for user's license if missing
            try:
                initialize_wallet_balances_for_license(lic)
            except Exception:
                pass

    wallet_filter = Q(user_id__iexact=user_id) | Q(licensee_id__in=candidates)
    if hasattr(WalletBalance, 'applicant'):
        wallet_filter |= Q(applicant=user)

    excise_wb = WalletBalance.objects.filter(
        wallet_filter,
        wallet_type__code__iexact='excise'
    ).order_by('-current_balance', 'wallet_balance_id').first()

    cess_wb = WalletBalance.objects.filter(
        wallet_filter,
        wallet_type__code__iexact='education_cess'
    ).order_by('-current_balance', 'wallet_balance_id').first()

    return Response({
        'excise_balance': float(excise_wb.current_balance) if excise_wb else 0.0,
        'education_cess_balance': float(cess_wb.current_balance) if cess_wb else 0.0,
    })
