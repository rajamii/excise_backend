from decimal import Decimal
import logging
import secrets
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from auth.workflow.models import Workflow
from auth.workflow.services import WorkflowService
from models.masters.license.models import License
from models.transactional.helpers import _get_role_stage_names, _get_stage_sets, _normalize_role, _collect_reachable_stage_names
from models.transactional.dashboard_cache import dashboard_counts_cache

from .models import SpecialPermitApplication, MasterDryDay
from .serializers import SpecialPermitApplicationSerializer, MasterDryDaySerializer

logger = logging.getLogger(__name__)


def _get_special_permit_workflow() -> Workflow | None:
    return (
        Workflow.objects.filter(name='Special Permit').order_by('id').first()
        or Workflow.objects.filter(name='Special Permission for Dry Day').order_by('id').first()
        or Workflow.objects.filter(name='License Approval').order_by('id').first()
    )


def _resolve_sub_category(license_obj):
    if license_obj.license_sub_category:
        return license_obj.license_sub_category
    
    # Try source application
    source_app = getattr(license_obj, 'source_application', None)
    if source_app:
        sub_cat = getattr(source_app, 'license_sub_category', None)
        if sub_cat:
            return sub_cat
        # Try new_license_application of source_app
        new_app = getattr(source_app, 'new_license_application', None)
        if new_app:
            sub_cat = getattr(new_app, 'license_sub_category', None)
            if sub_cat:
                return sub_cat
        # Try shop license of salesman application
        shop_license = getattr(source_app, 'license', None)
        if shop_license:
            if shop_license.license_sub_category:
                return shop_license.license_sub_category
            shop_src_app = getattr(shop_license, 'source_application', None)
            if shop_src_app:
                sub_cat = getattr(shop_src_app, 'license_sub_category', None)
                if sub_cat:
                    return sub_cat

    # Fallback to any NewLicenseApplication for this user
    from django.apps import apps
    NewLicenseApplication = apps.get_model('new_license_application', 'NewLicenseApplication')
    new_app = NewLicenseApplication.objects.filter(
        applicant=license_obj.applicant,
        license_sub_category__isnull=False
    ).order_by('-created_at').first()
    if new_app:
        return new_app.license_sub_category

    return None


def _resolve_location_category(license_obj) -> str | None:
    source_app = getattr(license_obj, 'source_application', None)
    if source_app:
        loc = getattr(source_app, 'location_category', None)
        if loc:
            return str(loc)
        # Try shop license
        shop_license = getattr(source_app, 'license', None)
        if shop_license:
            shop_src_app = getattr(shop_license, 'source_application', None)
            if shop_src_app:
                loc = getattr(shop_src_app, 'location_category', None)
                if loc:
                    return str(loc)
        # Try new_license_application
        new_app = getattr(source_app, 'new_license_application', None)
        if new_app:
            loc = getattr(new_app, 'location_category', None)
            if loc:
                return str(loc)

    # Fallback to any NewLicenseApplication for this user
    from django.apps import apps
    NewLicenseApplication = apps.get_model('new_license_application', 'NewLicenseApplication')
    new_app = NewLicenseApplication.objects.filter(
        applicant=license_obj.applicant,
        location_category__isnull=False
    ).exclude(location_category='').order_by('-created_at').first()
    if new_app:
        return str(new_app.location_category)

    return None


def calculate_special_permit_fee_raw(license_obj: License) -> dict:
    from models.masters.core.models import MasterFixedFee
    
    sub_category = _resolve_sub_category(license_obj)
    location_category = _resolve_location_category(license_obj)
    
    is_rural = False
    if location_category and str(location_category).strip().lower() == 'rural':
        is_rural = True
        
    dry_day_fee_type = getattr(sub_category, 'dry_day_fee_type', None)
    
    dry_day_fee = Decimal('0.00')
    if dry_day_fee_type == 'per_day':
        fee_obj = MasterFixedFee.objects.filter(fee_code='DRY_DAY_PER_DAY', is_active=True).first()
        if fee_obj:
            dry_day_fee = fee_obj.amount
    elif dry_day_fee_type == 'per_annum':
        if is_rural:
            fee_obj = MasterFixedFee.objects.filter(fee_code='DRY_DAY_ANNUAL_RURAL', is_active=True).first()
        else:
            fee_obj = MasterFixedFee.objects.filter(fee_code='DRY_DAY_ANNUAL_URBAN', is_active=True).first()
        if fee_obj:
            dry_day_fee = fee_obj.amount
                
    return {
        'dry_day_fee_type': dry_day_fee_type,
        'is_rural': is_rural,
        'dry_day_fee': Decimal(str(dry_day_fee))
    }


def calculate_special_permit_fee(app: SpecialPermitApplication) -> Decimal:
    from models.masters.core.models import MasterFixedFee
    
    location_category = _resolve_location_category(app.license)
    is_rural = False
    if location_category and str(location_category).strip().lower() == 'rural':
        is_rural = True
        
    duration = getattr(app, 'permission_duration', SpecialPermitApplication.PERMISSION_DURATION_PER_ANNUM)
    
    if duration == SpecialPermitApplication.PERMISSION_DURATION_PER_DAY:
        fee_obj = MasterFixedFee.objects.filter(fee_code='DRY_DAY_PER_DAY', is_active=True).first()
        base_fee = fee_obj.amount if fee_obj else Decimal('0.00')
        selected_dates = getattr(app, 'selected_dates', None)
        if isinstance(selected_dates, list) and len(selected_dates) > 0:
            return base_fee * len(selected_dates)
        return Decimal('0.00')
    else: # per_annum
        if is_rural:
            fee_obj = MasterFixedFee.objects.filter(fee_code='DRY_DAY_ANNUAL_RURAL', is_active=True).first()
        else:
            fee_obj = MasterFixedFee.objects.filter(fee_code='DRY_DAY_ANNUAL_URBAN', is_active=True).first()
        return fee_obj.amount if fee_obj else Decimal('0.00')


def _serialize_license(license_obj: License) -> dict:
    source_application = getattr(license_obj, 'source_application', None)
    establishment_name = None
    if source_application:
        for field in ('establishment_name', 'business_premises_name', 'company_name', 'applicant_name'):
            value = getattr(source_application, field, None)
            if value:
                establishment_name = str(value)
                break

    # If not found on direct source app (e.g. SalesmanBarmanModel), check shop license's source app
    if not establishment_name and source_application:
        shop_license = getattr(source_application, 'license', None)
        if shop_license:
            shop_src_app = getattr(shop_license, 'source_application', None)
            if shop_src_app:
                for field in ('establishment_name', 'business_premises_name', 'company_name', 'applicant_name'):
                    value = getattr(shop_src_app, field, None)
                    if value:
                        establishment_name = str(value)
                        break

    fee_details = calculate_special_permit_fee_raw(license_obj)
    resolved_sub_cat = _resolve_sub_category(license_obj)
    
    sub_cat_desc = getattr(resolved_sub_cat, 'description', None)
    if sub_cat_desc:
        fee_type = fee_details['dry_day_fee_type']
        if fee_type == 'per_annum':
            sub_cat_desc = f"{sub_cat_desc} (Dry Day Permit: Per Annum)"
        elif fee_type == 'per_day':
            sub_cat_desc = f"{sub_cat_desc} (Dry Day Permit: Per Day)"
        else:
            sub_cat_desc = f"{sub_cat_desc} (Dry Day Permit: None)"

    return {
        'license_id': license_obj.license_id,
        'district': getattr(license_obj.excise_district, 'district', None),
        'district_code': getattr(license_obj.excise_district, 'district_code', None),
        'license_category': getattr(license_obj.license_category, 'license_category', None),
        'license_sub_category': sub_cat_desc,
        'dry_day_fee_type': fee_details['dry_day_fee_type'],
        'is_rural': fee_details['is_rural'],
        'dry_day_fee': float(fee_details['dry_day_fee']),
        'establishment_name': establishment_name,
        'valid_up_to': license_obj.valid_up_to.isoformat() if license_obj.valid_up_to else None,
        'is_active': license_obj.is_active,
    }


def _visible_queryset(request):
    role = _normalize_role(request.user.role.name if getattr(request.user, 'role', None) else None)
    qs = SpecialPermitApplication.objects.select_related(
        'license',
        'applicant',
        'excise_district',
        'license_category',
        'license_sub_category',
        'workflow',
        'current_stage',
    )

    if role == 'licensee':
        return qs.filter(applicant=request.user)

    if role == 'district_user' and getattr(request.user, 'district', None):
        return qs.filter(excise_district=request.user.district)

    return qs


def _status_sets(workflow):
    if not workflow:
        return {
            'applied': set(),
            'pending': set(),
            'objection': set(),
            'approved': set(),
            'rejected': set(),
            'payment': set(),
        }
    stage_sets = _get_stage_sets(workflow.id)
    applied_stages = set(stage_sets['initial'])
    objection_stages = set(stage_sets['objection'])
    approved_stages = set(stage_sets['approved'])
    rejected_stages = set(stage_sets['rejected'])
    payment_stages = set(stage_sets['payment'])
    pending_stages = set(stage_sets['all']) - applied_stages - approved_stages - rejected_stages - objection_stages - payment_stages
    return {
        'applied': applied_stages,
        'pending': pending_stages,
        'objection': objection_stages,
        'approved': approved_stages,
        'rejected': rejected_stages,
        'payment': payment_stages,
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def eligible_licenses(request):
    now_dt = timezone.now()
    licenses = License.objects.filter(
        applicant=request.user,
        is_active=True,
        valid_up_to__gte=now_dt,
        source_type='new_license_application',
        license_category__is_special_permit_allowed=True
    ).select_related('excise_district', 'license_category', 'license_sub_category')
    return Response([_serialize_license(license_obj) for license_obj in licenses], status=status.HTTP_200_OK)


@api_view(['POST'])
@parser_classes([JSONParser])
@permission_classes([IsAuthenticated])
def create_special_permit_application(request):
    license_id = request.data.get('license') or request.data.get('license_id') or request.data.get('licenseId')
    if not license_id:
        return Response({'license': 'This field is required.'}, status=status.HTTP_400_BAD_REQUEST)

    license_obj = get_object_or_404(
        License.objects.select_related('excise_district', 'license_category', 'license_sub_category'),
        license_id=str(license_id),
    )
    if license_obj.applicant_id != request.user.id:
        return Response({'detail': 'You can only apply special permit for your own license.'}, status=status.HTTP_403_FORBIDDEN)
    if not license_obj.is_active or (license_obj.valid_up_to and license_obj.valid_up_to < timezone.now()):
        return Response({'detail': 'Special permit can be applied only against an active license.'}, status=status.HTTP_400_BAD_REQUEST)
    if not getattr(license_obj.license_category, 'is_special_permit_allowed', False):
        return Response(
            {'detail': 'Special permit is not available for this license category.'},
            status=status.HTTP_403_FORBIDDEN
        )

    permission_duration = request.data.get('permission_duration') or request.data.get('permissionDuration') or SpecialPermitApplication.PERMISSION_DURATION_PER_ANNUM
    selected_dates = request.data.get('selected_dates') or request.data.get('selectedDates') or None
    financial_year = request.data.get('financial_year') or request.data.get('financialYear') or SpecialPermitApplication.generate_fin_year()

    serializer = SpecialPermitApplicationSerializer(data={
        'license': license_obj.license_id,
        'financial_year': financial_year,
        'permission_duration': permission_duration,
        'selected_dates': selected_dates,
        'remarks': request.data.get('remarks', ''),
    })
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    workflow = _get_special_permit_workflow()
    if not workflow:
        return Response({'detail': 'Special Permit workflow is not configured.'}, status=status.HTTP_400_BAD_REQUEST)
    initial_stage = workflow.stages.filter(is_initial=True).order_by('id').first()
    if not initial_stage:
        return Response({'detail': 'Special Permit workflow has no initial stage.'}, status=status.HTTP_400_BAD_REQUEST)

    application = serializer.save(
        application_id=SpecialPermitApplication.generate_application_id(license_obj, financial_year),
        license=license_obj,
        applicant=request.user,
        excise_district=license_obj.excise_district,
        license_category=license_obj.license_category,
        license_sub_category=_resolve_sub_category(license_obj),
        workflow=workflow,
        current_stage=initial_stage,
    )
    WorkflowService.submit_application(
        application=application,
        user=request.user,
        remarks='Special Permit application submitted',
    )
    return Response(SpecialPermitApplicationSerializer(application).data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_special_permit_applications(request):
    return Response(SpecialPermitApplicationSerializer(_visible_queryset(request), many=True).data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def special_permit_detail(request, application_id):
    application = get_object_or_404(_visible_queryset(request), application_id=str(application_id))
    return Response(SpecialPermitApplicationSerializer(application).data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@dashboard_counts_cache("special_permit")
def dashboard_counts(request):
    role = _normalize_role(request.user.role.name if getattr(request.user, 'role', None) else None)
    workflow = _get_special_permit_workflow()
    if not workflow:
        return Response({
            'applied': 0, 'pending': 0, 'objection': 0, 'approved': 0, 'rejected': 0, 'awaiting_payment': 0
        }, status=status.HTTP_200_OK)

    stage_sets = _get_stage_sets(workflow.id)
    qs = _visible_queryset(request)

    month = request.query_params.get('month')
    year = request.query_params.get('year')
    if month:
        qs = qs.filter(created_at__month=month)
    if year:
        qs = qs.filter(created_at__year=year)

    if role == 'licensee':
        applied_stages = set(stage_sets['initial'])
        objection_stages = set(stage_sets['objection'])
        approved_stages = set(stage_sets['approved'])
        rejected_stages = set(stage_sets['rejected'])
        payment_stages = set(stage_sets['payment'])
        pending_stages = set(stage_sets['all']) - applied_stages - approved_stages - rejected_stages - objection_stages - payment_stages

        return Response({
            'applied': qs.filter(current_stage__name__in=applied_stages).count(),
            'pending': qs.filter(current_stage__name__in=pending_stages).count(),
            'objection': qs.filter(current_stage__name__in=objection_stages).count(),
            'approved': qs.filter(current_stage__name__in=approved_stages).count(),
            'rejected': qs.filter(current_stage__name__in=rejected_stages).count(),
            'awaiting_payment': qs.filter(current_stage__name__in=payment_stages).count(),
        }, status=status.HTTP_200_OK)

    if role in ('site_admin', 'single_window'):
        applied_stages = set(stage_sets['initial'])
        objection_stages = set(stage_sets['objection'])
        approved_stages = set(stage_sets['approved'])
        rejected_stages = set(stage_sets['rejected'])
        payment_stages = set(stage_sets['payment'])
        pending_stages = set(stage_sets['all']) - applied_stages - approved_stages - rejected_stages - objection_stages - payment_stages

        return Response({
            'applied': qs.filter(current_stage__name__in=applied_stages).count(),
            'pending': qs.filter(current_stage__name__in=pending_stages).count(),
            'objection': qs.filter(current_stage__name__in=objection_stages).count(),
            'approved': qs.filter(current_stage__name__in=approved_stages).count(),
            'rejected': qs.filter(current_stage__name__in=rejected_stages).count(),
            'awaiting_payment': qs.filter(current_stage__name__in=payment_stages).count(),
        }, status=status.HTTP_200_OK)

    # For District User, Commissioner, etc.
    role_stage_names = _get_role_stage_names(request.user, workflow.id)
    if role_stage_names:
        role_objection_stages = set(stage_sets['objection'])
        pending_stages = set(role_stage_names) | role_objection_stages
        reachable_from_role = _collect_reachable_stage_names(workflow.id, set(role_stage_names))
        role_rejected_stages = set(stage_sets['rejected'])

        approved_stages = set(stage_sets['approved'])
        payment_stages = set(stage_sets['payment'])
        forward_stages = set(reachable_from_role) - pending_stages - role_rejected_stages

        return Response({
            'applied': 0,
            'pending': qs.filter(current_stage__name__in=pending_stages).count(),
            'objection': qs.filter(current_stage__name__in=role_objection_stages).count(),
            'approved': qs.filter(current_stage__name__in=approved_stages | forward_stages).count(),
            'rejected': qs.filter(current_stage__name__in=role_rejected_stages).count(),
            'awaiting_payment': qs.filter(current_stage__name__in=payment_stages).count(),
        }, status=status.HTTP_200_OK)

    return Response({
        'applied': 0, 'pending': 0, 'objection': 0, 'approved': 0, 'rejected': 0, 'awaiting_payment': 0
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def application_group(request):
    role = _normalize_role(request.user.role.name if getattr(request.user, 'role', None) else None)
    workflow = _get_special_permit_workflow()
    if not workflow:
        return Response({
            'applied': [], 'pending': [], 'objection': [], 'approved': [], 'rejected': [], 'awaiting_payment': []
        }, status=status.HTTP_200_OK)

    stage_sets = _get_stage_sets(workflow.id)
    qs = _visible_queryset(request)

    if role == 'licensee':
        applied_stages = set(stage_sets['initial'])
        objection_stages = set(stage_sets['objection'])
        approved_stages = set(stage_sets['approved'])
        rejected_stages = set(stage_sets['rejected'])
        payment_stages = set(stage_sets['payment'])
        pending_stages = set(stage_sets['all']) - applied_stages - approved_stages - rejected_stages - objection_stages - payment_stages

        return Response({
            'applied': SpecialPermitApplicationSerializer(qs.filter(current_stage__name__in=applied_stages), many=True).data,
            'pending': SpecialPermitApplicationSerializer(qs.filter(current_stage__name__in=pending_stages), many=True).data,
            'objection': SpecialPermitApplicationSerializer(qs.filter(current_stage__name__in=objection_stages), many=True).data,
            'approved': SpecialPermitApplicationSerializer(qs.filter(current_stage__name__in=approved_stages), many=True).data,
            'rejected': SpecialPermitApplicationSerializer(qs.filter(current_stage__name__in=rejected_stages), many=True).data,
            'awaiting_payment': SpecialPermitApplicationSerializer(qs.filter(current_stage__name__in=payment_stages), many=True).data,
        }, status=status.HTTP_200_OK)

    if role in ('site_admin', 'single_window'):
        applied_stages = set(stage_sets['initial'])
        objection_stages = set(stage_sets['objection'])
        approved_stages = set(stage_sets['approved'])
        rejected_stages = set(stage_sets['rejected'])
        payment_stages = set(stage_sets['payment'])
        pending_stages = set(stage_sets['all']) - applied_stages - approved_stages - rejected_stages - objection_stages - payment_stages

        return Response({
            'applied': SpecialPermitApplicationSerializer(qs.filter(current_stage__name__in=applied_stages), many=True).data,
            'pending': SpecialPermitApplicationSerializer(qs.filter(current_stage__name__in=pending_stages), many=True).data,
            'objection': SpecialPermitApplicationSerializer(qs.filter(current_stage__name__in=objection_stages), many=True).data,
            'approved': SpecialPermitApplicationSerializer(qs.filter(current_stage__name__in=approved_stages), many=True).data,
            'rejected': SpecialPermitApplicationSerializer(qs.filter(current_stage__name__in=rejected_stages), many=True).data,
            'awaiting_payment': SpecialPermitApplicationSerializer(qs.filter(current_stage__name__in=payment_stages), many=True).data,
        }, status=status.HTTP_200_OK)

    # For District User, Commissioner, etc.
    role_stage_names = _get_role_stage_names(request.user, workflow.id)
    if role_stage_names:
        role_objection_stages = set(stage_sets['objection'])
        pending_stages = set(role_stage_names) | role_objection_stages
        reachable_from_role = _collect_reachable_stage_names(workflow.id, set(role_stage_names))
        role_rejected_stages = set(stage_sets['rejected'])

        approved_stages = set(stage_sets['approved'])
        payment_stages = set(stage_sets['payment'])
        forward_stages = set(reachable_from_role) - pending_stages - role_rejected_stages

        return Response({
            'applied': [],
            'pending': SpecialPermitApplicationSerializer(qs.filter(current_stage__name__in=pending_stages), many=True).data,
            'objection': SpecialPermitApplicationSerializer(qs.filter(current_stage__name__in=role_objection_stages), many=True).data,
            'approved': SpecialPermitApplicationSerializer(qs.filter(current_stage__name__in=approved_stages | forward_stages), many=True).data,
            'rejected': SpecialPermitApplicationSerializer(qs.filter(current_stage__name__in=role_rejected_stages), many=True).data,
            'awaiting_payment': SpecialPermitApplicationSerializer(qs.filter(current_stage__name__in=payment_stages), many=True).data,
        }, status=status.HTTP_200_OK)

    return Response({
        'applied': [], 'pending': [], 'objection': [], 'approved': [], 'rejected': [], 'awaiting_payment': []
    }, status=status.HTTP_200_OK)


def _sync_special_permit_payment_status(application, user=None):
    workflow = application.workflow
    if workflow:
        approved_stage = (
            workflow.stages.filter(name__icontains='approved').order_by('id').first() or
            workflow.stages.filter(is_final=True).order_by('id').first()
        )
        if approved_stage:
            try:
                WorkflowService.advance_stage(
                    application=application,
                    user=user or application.applicant,
                    target_stage=approved_stage,
                    context={"action": "PAY"},
                    remarks="Special Permit fee paid successfully. Application approved."
                )
                application.is_approved = True
                application.save(update_fields=['is_approved'])
            except Exception as e:
                logger.error("Failed to advance stage on payment: %s", e)
                application.current_stage = approved_stage
                application.is_approved = True
                application.save(update_fields=['current_stage', 'is_approved'])


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def pay_special_permit_fee_wallet(request, application_id):
    application = get_object_or_404(SpecialPermitApplication, application_id=str(application_id))
    if application.applicant_id != request.user.id:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    stage_name = str(getattr(getattr(application, "current_stage", None), "name", "") or "").strip().lower()
    if stage_name and "awaiting payment" not in stage_name and "payment" not in stage_name:
        return Response({"detail": "Payment is not allowed at the current stage."}, status=status.HTTP_400_BAD_REQUEST)

    license_obj = application.license
    amount = calculate_special_permit_fee(application)
    if amount <= Decimal('0.00'):
        return Response({"detail": "Special permit fee is not configured or is zero."}, status=status.HTTP_400_BAD_REQUEST)

    wallet_licensee_id = str(license_obj.license_id)

    from models.transactional.license_renewal_application.views import _resolve_hoa_code
    license_fee_hoa = _resolve_hoa_code(module_type="other", wallet_type="license_fee")

    txn_id = None
    try:
        from models.transactional.payment_gateway.models import PaymentBilldeskTransaction
        from models.transactional.wallet.models import WalletTransaction
        from datetime import timedelta
        
        candidates = [
            str(request.user.username).strip(),
            str(wallet_licensee_id).strip(),
            str(application.application_id).strip()
        ]
        time_limit = timezone.now() - timedelta(days=2)
        
        recent_txs = PaymentBilldeskTransaction.objects.filter(
            payer_id__in=candidates,
            payment_status="S",
            transaction_amount=Decimal(str(amount)),
            transaction_date__gte=time_limit
        ).order_by("-transaction_date")
        
        for tx in recent_txs:
            if not WalletTransaction.objects.filter(transaction_id=tx.utr, entry_type="DR").exists():
                txn_id = tx.utr
                break
                
        if not txn_id:
            recent_txs_any = PaymentBilldeskTransaction.objects.filter(
                payer_id__in=candidates,
                payment_status="S",
                transaction_date__gte=time_limit
            ).order_by("-transaction_date")
            for tx in recent_txs_any:
                if not WalletTransaction.objects.filter(transaction_id=tx.utr, entry_type="DR").exists():
                    txn_id = tx.utr
                    break
    except Exception as e:
        logger.warning("Failed to link BillDesk UTR to wallet special permit payment: %s", e)

    if not txn_id:
        txn_id = secrets.token_hex(12).upper()

    try:
        from models.transactional.wallet.wallet_service import debit_wallet_balance
        debit_wallet_balance(
            transaction_id=txn_id,
            licensee_id=wallet_licensee_id,
            wallet_type="license_fee",
            head_of_account=license_fee_hoa,
            amount=Decimal(str(amount)),
            user_id=str(getattr(request.user, "username", "") or "").strip(),
            remarks=f"Special permit fee paid for {application.application_id}",
            reference_no=application.application_id,
        )
    except Exception as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    application.is_fee_paid = True
    application.save(update_fields=["is_fee_paid"])

    _sync_special_permit_payment_status(application, request.user)

    return Response({
        "success": True,
        "application_id": application.application_id,
        "is_fee_paid": True,
        "current_stage": getattr(application.current_stage, "name", None)
    }, status=status.HTTP_200_OK)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def master_dry_day_list_create(request):
    if request.method == 'GET':
        financial_year = request.query_params.get('financial_year')
        if financial_year:
            obj = MasterDryDay.objects.filter(financial_year=financial_year).first()
            if obj:
                serializer = MasterDryDaySerializer(obj)
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                return Response({
                    'financial_year': financial_year,
                    'allowed_dates': []
                }, status=status.HTTP_200_OK)
        else:
            objs = MasterDryDay.objects.all()
            serializer = MasterDryDaySerializer(objs, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    elif request.method == 'POST':
        role_name = request.user.role.name if getattr(request.user, 'role', None) else ''
        role_name_lower = role_name.lower().replace('_', '').replace(' ', '')
        if 'siteadmin' not in role_name_lower:
            return Response({"detail": "Only Site Admin is allowed to update the dry day calendar."}, status=status.HTTP_403_FORBIDDEN)

        financial_year = request.data.get('financial_year')
        allowed_dates = request.data.get('allowed_dates', [])
        if not financial_year:
            return Response({"detail": "financial_year is required."}, status=status.HTTP_400_BAD_REQUEST)

        obj, created = MasterDryDay.objects.get_or_create(financial_year=financial_year)
        obj.allowed_dates = allowed_dates
        obj.save()

        serializer = MasterDryDaySerializer(obj)
        return Response(serializer.data, status=status.HTTP_200_OK)

