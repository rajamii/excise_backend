from rest_framework import status, views, generics
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from decimal import Decimal
import logging
import re
from .serializers import (
    TransitPermitSubmissionSerializer,
    EnaTransitPermitDetailSerializer,
    PublicTransitPermitDetailSerializer,
)
from .models import EnaTransitPermitDetail
from auth.workflow.constants import WORKFLOW_IDS
from models.transactional.supply_chain.access_control import (
    has_workflow_access,
    scope_by_profile_or_workflow,
    transition_matches,
)

logger = logging.getLogger(__name__)


def _get_user_display_name(user) -> str:
    """Return a human-readable display name for a user (first + middle + last name, falling back to username)."""
    if user is None:
        return 'System'
    first = (getattr(user, 'first_name', '') or '').strip()
    middle = (getattr(user, 'middle_name', '') or '').strip()
    last = (getattr(user, 'last_name', '') or '').strip()
    parts = [p for p in [first, middle, last] if p]
    full = ' '.join(parts)
    return full if full else (getattr(user, 'username', None) or 'System')


def _get_size_ml_value(item) -> int:
    """
    Return the ml value for a permit row.

    After migration, `item.size_ml` is a MasterLiquorCategory FK, so `int(item.size_ml)` yields ml.
    """
    try:
        if getattr(item, 'size_ml_id', None):
            return int(item.size_ml)
    except Exception:
        pass

    try:
        return int(getattr(item, 'size_ml', 0) or 0)
    except Exception:
        return 0


class SubmitTransitPermitAPIView(views.APIView):
    permission_classes = [IsAuthenticated]

    def _parse_int_from_size(self, value) -> int:
        """
        Parse pack size ml from common UI inputs: 750, "750", "750ml", "750 ML".
        """
        try:
            if value is None:
                return 0
            if isinstance(value, int):
                return int(value)
            if isinstance(value, float):
                return int(value)
            raw = str(value).strip().lower()
            if not raw:
                return 0
            digits = re.findall(r'\d+', raw)
            return int(digits[0]) if digits else 0
        except Exception:
            return 0

    def _resolve_master_liquor_category(self, size_ml):
        from models.masters.supply_chain.liquor_data.models import MasterLiquorCategory

        normalized = self._parse_int_from_size(size_ml)

        obj, _ = MasterLiquorCategory.objects.get_or_create(size_ml=normalized)
        return obj

    def _resolve_master_liquor_type(self, liquor_type):
        from models.masters.supply_chain.liquor_data.models import MasterLiquorType

        name = str(liquor_type or '').strip() or 'Other'
        obj, _ = MasterLiquorType.objects.get_or_create(liquor_type=name)
        return obj

    def _resolve_brand_warehouse_row(self, brand_name: str, size_ml: int, licensee_id: str):
        try:
            from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouse

            normalized_brand = str(brand_name or '').strip()
            size_ml_val = int(size_ml or 0)
            normalized_license = str(licensee_id or '').strip()
            if not normalized_brand or size_ml_val <= 0:
                return None

            base = BrandWarehouse.objects.select_related(
                'brand', 'factory', 'liquor_type', 'capacity_size'
            ).filter(
                brand__brand_name__iexact=normalized_brand,
                capacity_size__size_ml=size_ml_val,
            )

            row = None
            if normalized_license:
                row = base.filter(license_id__iexact=normalized_license).first()
            if not row:
                row = base.first()
            return row
        except Exception:
            return None

    def _resolve_liquor_data_row(self, warehouse_row, brand_name: str, size_ml: int):
        try:
            from models.masters.supply_chain.liquor_data.models import LiquorData

            liquor_data_id = getattr(warehouse_row, 'liquor_data_id', None) if warehouse_row else None
            if liquor_data_id:
                return LiquorData.objects.filter(id=liquor_data_id).first()

            normalized_brand = str(brand_name or '').strip()
            size_ml_val = int(size_ml or 0)
            if not normalized_brand or size_ml_val <= 0:
                return None

            return (
                LiquorData.objects.filter(brand_name__iexact=normalized_brand, pack_size_ml=size_ml_val)
                .order_by('-updated_at', '-id')
                .first()
            )
        except Exception:
            return None

    def _enrich_product_payload_from_masters(self, product: dict, licensee_id: str) -> dict:
        """
        Ensure product payload has brand owner, manufacturing unit, liquor type and rates.

        Some deployments/UI flows submit only brand/size/cases (without rates/meta). To keep
        server-side data consistent (and to make hosted environment work), derive missing
        values from BrandWarehouse + LiquorData.
        """
        if not isinstance(product, dict):
            return product

        brand = str(product.get('brand') or '').strip()
        size_ml_val = self._parse_int_from_size(product.get('size'))
        if not brand or size_ml_val <= 0:
            return product

        warehouse_row = self._resolve_brand_warehouse_row(brand, size_ml_val, licensee_id)
        liquor_data_row = self._resolve_liquor_data_row(warehouse_row, brand, size_ml_val)

        def has_value(v) -> bool:
            return str(v or '').strip() != ''

        # Meta fields
        if not has_value(product.get('manufacturing_unit_name')):
            manufacturing_unit = ''
            if warehouse_row:
                manufacturing_unit = str(getattr(warehouse_row, 'distillery_name', '') or '').strip()
            if not manufacturing_unit and liquor_data_row:
                manufacturing_unit = str(getattr(liquor_data_row, 'manufacturing_unit_name', '') or '').strip()
            if manufacturing_unit:
                product['manufacturing_unit_name'] = manufacturing_unit

        if not has_value(product.get('brand_owner')) and liquor_data_row:
            brand_owner = str(getattr(liquor_data_row, 'brand_owner', '') or '').strip()
            if brand_owner:
                product['brand_owner'] = brand_owner

        if not has_value(product.get('liquor_type')):
            liquor_type_name = ''
            try:
                if warehouse_row and getattr(warehouse_row, 'liquor_type', None):
                    liquor_type_name = str(warehouse_row.liquor_type or '').strip()
            except Exception:
                liquor_type_name = ''
            if not liquor_type_name and liquor_data_row:
                liquor_type_name = str(getattr(liquor_data_row, 'liquor_type', '') or '').strip()
            if liquor_type_name:
                product['liquor_type'] = liquor_type_name

        # Rate fields (per case)
        def ensure_rate(product_key: str, warehouse_attr: str):
            try:
                current = Decimal(str(product.get(product_key, 0) or 0))
            except Exception:
                current = Decimal('0')

            if current > 0:
                return

            if not warehouse_row:
                return

            try:
                derived = Decimal(str(getattr(warehouse_row, warehouse_attr, 0) or 0))
            except Exception:
                derived = Decimal('0')

            if derived > 0:
                product[product_key] = float(derived)

        ensure_rate('ex_factory_price', 'ex_factory_price_rs_per_case')
        ensure_rate('excise_duty', 'excise_duty_rs_per_case')
        ensure_rate('education_cess', 'education_cess_rs_per_case')
        ensure_rate('additional_excise', 'additional_excise_duty_rs_per_case')

        return product

    def _resolve_submit_target_stage(self):
        """
        Resolve submit target stage from workflow table dynamically.
        Resolves the target stage by DB transition: initial_stage --PAY--> next_stage.
        """
        from auth.workflow.models import Workflow, WorkflowStage, WorkflowTransition

        workflow_obj = Workflow.objects.filter(id=WORKFLOW_IDS['TRANSIT_PERMIT']).first()
        if not workflow_obj:
            return None, None

        initial_stage = WorkflowStage.objects.filter(workflow=workflow_obj, is_initial=True).first()
        if not initial_stage:
            return workflow_obj, None

        pay_transitions = WorkflowTransition.objects.filter(
            workflow=workflow_obj,
            from_stage=initial_stage
        )
        for transition in pay_transitions:
            cond = transition.condition or {}
            if str(cond.get('action') or '').strip().upper() == 'PAY':
                return workflow_obj, transition.to_stage

        return workflow_obj, None

    def _resolve_stage_from_status_code(self, workflow_obj, status_code):
        """
        Resolve a stage by status_code using workflow graph/actions, not stage names.
        """
        from auth.workflow.models import WorkflowStage, WorkflowTransition

        normalized = str(status_code or '').strip().upper()
        initial_stage = WorkflowStage.objects.filter(workflow=workflow_obj, is_initial=True).first()
        if not initial_stage:
            return None

        if normalized == 'TRP_01':
            return initial_stage

        outgoing = WorkflowTransition.objects.filter(workflow=workflow_obj, from_stage=initial_stage)
        if normalized == 'TRP_02':
            for t in outgoing:
                if str((t.condition or {}).get('action') or '').strip().upper() == 'PAY':
                    return t.to_stage

        if normalized in {'TRP_03', 'TRP_04'}:
            pay_stage = None
            for t in outgoing:
                if str((t.condition or {}).get('action') or '').strip().upper() == 'PAY':
                    pay_stage = t.to_stage
                    break
            if not pay_stage:
                return None
            second_hop = WorkflowTransition.objects.filter(workflow=workflow_obj, from_stage=pay_stage)
            for t in second_hop:
                action = str((t.condition or {}).get('action') or '').strip().upper()
                if normalized == 'TRP_03' and action == 'APPROVE':
                    return t.to_stage
                if normalized == 'TRP_04' and action == 'REJECT':
                    return t.to_stage

        return None

    def _generate_transit_ref(self) -> str:
        existing_refs = list(EnaTransitPermitDetail.objects.values_list('bill_no', flat=True))
        try:
            from models.transactional.payment.models import WalletTransaction
            existing_refs.extend(
                WalletTransaction.objects.filter(source_module='transit_permit')
                .exclude(reference_no__isnull=True)
                .exclude(reference_no='')
                .values_list('reference_no', flat=True)
            )
        except Exception:
            pass

        # Strict format: TRP/<number>/EXCISE
        pattern = r'^TRP/0*(\d+)/EXCISE$'
        numbers = []

        for ref in existing_refs:
            normalized_ref = str(ref or '').strip().upper()
            match = re.match(pattern, normalized_ref)
            if match:
                numbers.append(int(match.group(1)))

        next_number = (max(numbers) + 1) if numbers else 1
        return f"TRP/{next_number:02d}/EXCISE"

    def _resolve_approved_license_id(self, user) -> str:
        """
        Resolve currently active/approved license id (NA/... preferred) for transit records.
        """
        raw_profile_id = ''
        if hasattr(user, 'supply_chain_profile'):
            raw_profile_id = str(getattr(user.supply_chain_profile, 'licensee_id', '') or '').strip()

        from models.masters.license.models import License

        active_licenses = License.objects.filter(
            applicant=user,
            source_type='new_license_application',
            is_active=True
        ).order_by('-issue_date')

        if raw_profile_id:
            hit = active_licenses.filter(
                Q(license_id=raw_profile_id) | Q(source_object_id=raw_profile_id)
            ).first()
            if hit and hit.license_id:
                return str(hit.license_id).strip()

            if raw_profile_id.startswith('NLI/'):
                na_alias = f"NA/{raw_profile_id[4:]}"
                hit_alias = active_licenses.filter(license_id=na_alias).first()
                if hit_alias and hit_alias.license_id:
                    return str(hit_alias.license_id).strip()

            if raw_profile_id.startswith('NA/'):
                return raw_profile_id

        latest = active_licenses.first()
        if latest and latest.license_id:
            return str(latest.license_id).strip()

        return raw_profile_id

    def _debit_wallet_balances_for_submit(self, user, license_id: str, bill_no: str, permit_rows):
        """
        Debit Excise and Education Cess wallets at submit time and persist wallet transactions.
        Additional excise is debited from excise wallet.
        """
        from models.transactional.payment.models import WalletBalance, WalletTransaction

        license_id = str(license_id or '').strip()
        if not license_id:
            raise ValueError("Unable to resolve approved license id for wallet deduction.")

        excise_total = Decimal("0.00")
        education_total = Decimal("0.00")
        for row in permit_rows:
            excise_total += Decimal(str(row.total_excise_duty or 0)) + Decimal(str(row.total_additional_excise or 0))
            education_total += Decimal(str(row.total_education_cess or 0))

        if excise_total <= 0 and education_total <= 0:
            return

        username = str(getattr(user, 'username', '') or '')

        with transaction.atomic():
            excise_wallet = (
                WalletBalance.objects.select_for_update()
                .filter(licensee_id=license_id, wallet_type__iexact='excise')
                .order_by('wallet_balance_id')
                .first()
            )
            education_wallet = (
                WalletBalance.objects.select_for_update()
                .filter(licensee_id=license_id, wallet_type__iexact='education_cess')
                .order_by('wallet_balance_id')
                .first()
            )

            if excise_total > 0 and not excise_wallet:
                raise ValueError(f"Excise wallet not found for license_id={license_id}")
            if education_total > 0 and not education_wallet:
                raise ValueError(f"Education cess wallet not found for license_id={license_id}")

            if excise_wallet and Decimal(str(excise_wallet.current_balance or 0)) < excise_total:
                raise ValueError(
                    f"Insufficient Excise Wallet Balance. Available: {excise_wallet.current_balance}, Required: {excise_total}"
                )
            if education_wallet and Decimal(str(education_wallet.current_balance or 0)) < education_total:
                raise ValueError(
                    f"Insufficient Education Cess Wallet Balance. Available: {education_wallet.current_balance}, Required: {education_total}"
                )

            now_ts = timezone.now()

            if excise_wallet and excise_total > 0:
                excise_transaction_id = f"TRP-{bill_no}-EXCISE"
                excise_exists = WalletTransaction.objects.filter(
                    transaction_id=excise_transaction_id,
                    head_of_account=excise_wallet.head_of_account,
                    entry_type='DR',
                    source_module='transit_permit',
                ).exists()
                if excise_exists:
                    raise ValueError(
                        f"Transit wallet debit already exists for bill {bill_no}. "
                        "Please refresh and continue with the latest reference."
                    )

                before = Decimal(str(excise_wallet.current_balance or 0))
                after = before - excise_total
                excise_wallet.current_balance = after
                excise_wallet.total_debit = Decimal(str(excise_wallet.total_debit or 0)) + excise_total
                excise_wallet.last_updated_at = now_ts
                excise_wallet.save(update_fields=['current_balance', 'total_debit', 'last_updated_at'])

                WalletTransaction.objects.create(
                    wallet_balance=excise_wallet,
                    transaction_id=excise_transaction_id,
                    licensee_id=license_id,
                    licensee_name=excise_wallet.licensee_name,
                    user_id=username or excise_wallet.user_id,
                    module_type=excise_wallet.module_type,
                    wallet_type=excise_wallet.wallet_type,
                    head_of_account=excise_wallet.head_of_account,
                    entry_type='DR',
                    transaction_type='debit',
                    amount=excise_total,
                    balance_before=before,
                    balance_after=after,
                    reference_no=bill_no,
                    source_module='transit_permit',
                    payment_status='success',
                    remarks='Transit permit submit debit (excise + additional excise)',
                    created_at=now_ts,
                )

            if education_wallet and education_total > 0:
                education_transaction_id = f"TRP-{bill_no}-EDUCATION"
                education_exists = WalletTransaction.objects.filter(
                    transaction_id=education_transaction_id,
                    head_of_account=education_wallet.head_of_account,
                    entry_type='DR',
                    source_module='transit_permit',
                ).exists()
                if education_exists:
                    raise ValueError(
                        f"Transit education-cess debit already exists for bill {bill_no}. "
                        "Please refresh and continue with the latest reference."
                    )

                before = Decimal(str(education_wallet.current_balance or 0))
                after = before - education_total
                education_wallet.current_balance = after
                education_wallet.total_debit = Decimal(str(education_wallet.total_debit or 0)) + education_total
                education_wallet.last_updated_at = now_ts
                education_wallet.save(update_fields=['current_balance', 'total_debit', 'last_updated_at'])

                WalletTransaction.objects.create(
                    wallet_balance=education_wallet,
                    transaction_id=education_transaction_id,
                    licensee_id=license_id,
                    licensee_name=education_wallet.licensee_name,
                    user_id=username or education_wallet.user_id,
                    module_type=education_wallet.module_type,
                    wallet_type=education_wallet.wallet_type,
                    head_of_account=education_wallet.head_of_account,
                    entry_type='DR',
                    transaction_type='debit',
                    amount=education_total,
                    balance_before=before,
                    balance_after=after,
                    reference_no=bill_no,
                    source_module='transit_permit',
                    payment_status='success',
                    remarks='Transit permit submit debit (education cess)',
                    created_at=now_ts,
                )

    def _create_utilization_and_deduct_stock_for_submit(self, permit_rows, license_id: str, user=None):
        """
        Create BrandWarehouseUtilization rows immediately on submit and deduct stock.
        This keeps OIC utilization dashboard in sync without waiting for a separate PAY action.
        """
        from models.transactional.supply_chain.brand_warehouse.models import (
            BrandWarehouse,
            BrandWarehouseUtilization,
        )
        from models.masters.supply_chain.transit_permit.models import BrandMlInCases

        normalized_license_id = str(license_id or '').strip()

        for item in permit_rows:
            item_license_id = str(getattr(item, 'licensee_id', '') or '').strip() or normalized_license_id

            warehouse_qs = BrandWarehouse.objects.filter(
                capacity_size__size_ml=_get_size_ml_value(item),
            )
            if item_license_id:
                warehouse_qs = warehouse_qs.filter(license_id=item_license_id)

            warehouse_entry = warehouse_qs.filter(brand__brand_name__iexact=item.brand).first()
            if not warehouse_entry:
                warehouse_entry = warehouse_qs.filter(brand__brand_name__icontains=item.brand).first()
            if not warehouse_entry:
                raise ValueError(
                    f"Brand warehouse entry not found for brand={item.brand}, size={_get_size_ml_value(item)}, "
                    f"license_id={item_license_id or 'N/A'}"
                )

            resolved_license_id = item_license_id or str(getattr(warehouse_entry, 'license_id', '') or '').strip()

            utilization_exists = BrandWarehouseUtilization.objects.filter(
                permit_no=item.bill_no,
                brand_warehouse=warehouse_entry,
                distributor=item.sole_distributor_name,
                depot_address=item.depot_address,
                vehicle=item.vehicle_number,
                cases=item.cases,
                quantity=int(item.cases) * int(item.bottles_per_case or 0 or 1),
            ).exists()
            if utilization_exists:
                continue

            bottles_per_case = int(item.bottles_per_case or 0)
            if bottles_per_case <= 0:
                ml_config = BrandMlInCases.objects.filter(ml=int(warehouse_entry.capacity_size)).first()
                bottles_per_case = int(ml_config.pieces_in_case) if ml_config and ml_config.pieces_in_case else 1

            total_pieces = int(item.cases) * bottles_per_case

            BrandWarehouseUtilization.objects.create(
                brand_warehouse=warehouse_entry,
                license_id=resolved_license_id or None,
                permit_no=item.bill_no,
                date=item.date,
                distributor=item.sole_distributor_name,
                depot_address=item.depot_address,
                vehicle=item.vehicle_number,
                quantity=total_pieces,
                cases=item.cases,
                bottles_per_case=bottles_per_case,
                status='APPROVED',
                approved_by=_get_user_display_name(user) if user else 'System (Submit Auto-Deduction)',
                approval_date=timezone.now(),
            )

    def post(self, request):
        serializer = TransitPermitSubmissionSerializer(data=request.data)
        if serializer.is_valid():
            data = serializer.validated_data
            bill_no = self._generate_transit_ref()
            
            # 1. Uniqueness Check (Application Level)
            if EnaTransitPermitDetail.objects.filter(bill_no=bill_no).exists():
                return Response({
                    "status": "error",
                    "message": "Submission failed. Bill Number already exists."
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # 2. Prepare common data
            sole_distributor_name = data['sole_distributor']
            date = data['date']
            depot_address = data['depot_address']
            vehicle_number = data['vehicle_number']
            products = data['products'] 
            
            # Store approved license id in permit rows for profile-scoped dashboards.
            licensee_id = self._resolve_approved_license_id(request.user)
            if not (str(licensee_id).startswith('NA/') or str(licensee_id).startswith('NLI/')):
                return Response({
                    "status": "error",
                    "message": "Approved license id not found for this profile. Please switch to the approved unit/profile first."
                }, status=status.HTTP_400_BAD_REQUEST)
            
            created_records = []
            
            # 3. Save each product as a new row
            try:
                with transaction.atomic():
                    workflow_obj, paid_stage = self._resolve_submit_target_stage()
                    if not paid_stage:
                        return Response({
                            "status": "error",
                            "message": "Transit workflow misconfigured: missing PAY transition from initial stage."
                        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                    submit_message = (
                        str(getattr(paid_stage, 'description', '') or '').strip()
                        if paid_stage else
                        "Transit Permit submitted, payment deducted, and forwarded to Officer In-Charge."
                    )

                    for product in products:
                        product = self._enrich_product_payload_from_masters(product, licensee_id)
                        obj = EnaTransitPermitDetail(
                            bill_no=bill_no,
                            sole_distributor_name=sole_distributor_name,
                            date=date,
                            depot_address=depot_address,
                            vehicle_number=vehicle_number,
                            licensee_id=licensee_id,
                            
                            brand=product.get('brand'),
                            size_ml=self._resolve_master_liquor_category(product.get('size')),
                            cases=product.get('cases'),
                            bottle_type=product.get('bottle_type', ''), # Save bottle_type

                            # New fields
                            brand_owner=product.get('brand_owner', ''),
                            liquor_type=self._resolve_master_liquor_type(product.get('liquor_type', '')),
                            exfactory_price_rs_per_case=product.get('ex_factory_price', 0.00),
                            
                            excise_duty_rs_per_case=product.get('excise_duty', 0.00),
                            education_cess_rs_per_case=product.get('education_cess', 0.00),
                            additional_excise_duty_rs_per_case=product.get('additional_excise', 0.00),
                            
                            # Save Historical Bottles Per Case
                            bottles_per_case=self._get_bottles_per_case(product.get('size'), product.get('brand')),
                            
                            manufacturing_unit_name=product.get('manufacturing_unit_name', ''),

                            # Calculated totals
                            total_excise_duty=float(product.get('excise_duty', 0.00)) * int(product.get('cases', 0)),
                            total_education_cess=float(product.get('education_cess', 0.00)) * int(product.get('cases', 0)),
                            total_additional_excise=float(product.get('additional_excise', 0.00)) * int(product.get('cases', 0)),
                            total_amount=(
                                (float(product.get('excise_duty', 0.00)) + 
                                 float(product.get('education_cess', 0.00)) + 
                                 float(product.get('additional_excise', 0.00))) * int(product.get('cases', 0))
                            )
                        )

                        # Payment is completed on submit; forward directly to OIC stage from workflow table.
                        if paid_stage:
                            obj.status = paid_stage.name
                            obj.status_code = 'TRP_02'
                            obj.current_stage = paid_stage
                        if workflow_obj:
                            obj.workflow = workflow_obj
                        obj.save()
                        if obj.current_stage and obj.status != obj.current_stage.name:
                            obj.status = obj.current_stage.name
                            obj.save(update_fields=['status'])
                        created_records.append(obj)

                    # Deduct wallet immediately on submit from excise + education wallets.
                    self._debit_wallet_balances_for_submit(
                        user=request.user,
                        license_id=licensee_id,
                        bill_no=bill_no,
                        permit_rows=created_records
                    )

                    # Create utilization entries and deduct warehouse stock immediately.
                    self._create_utilization_and_deduct_stock_for_submit(
                        permit_rows=created_records,
                        license_id=licensee_id,
                        user=request.user,
                    )
                
                return Response({
                    "status": "success",
                    "message": submit_message,
                    "bill_no": bill_no,
                    "count": len(created_records)
                }, status=status.HTTP_201_CREATED)
                
            except ValueError as e:
                 return Response({
                    "status": "error",
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                 return Response({
                    "status": "error",
                    "message": str(e)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        logger.debug("Transit permit submission validation errors: %s", serializer.errors)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def _get_bottles_per_case(self, size_ml, brand_name):
        try:
            from models.masters.supply_chain.transit_permit.models import BrandMlInCases
            # Try to find specific configuration for this size
            if size_ml:
                ml_config = BrandMlInCases.objects.filter(ml=int(size_ml)).first()
                if ml_config:
                    return ml_config.pieces_in_case
        except Exception as e:
            logger.exception(
                "Error fetching bottles per case (brand=%s size_ml=%s). Using fallback.",
                brand_name,
                size_ml,
            )
        
        # Fallbacks
        try:
            size_ml = int(size_ml)
            if size_ml == 750: return 12
            if size_ml == 375: return 24
            if size_ml == 180: return 48
            if size_ml == 650: return 12
            if size_ml == 90: return 96
        except:
            pass
            
        return 12 # Ultimate default

class GetTransitPermitAPIView(generics.ListAPIView):
    serializer_class = EnaTransitPermitDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = EnaTransitPermitDetail.objects.all().order_by('-id') # Order by newest first

        queryset = scope_by_profile_or_workflow(
            self.request.user,
            queryset,
            WORKFLOW_IDS['TRANSIT_PERMIT'],
            licensee_field='licensee_id'
        )

        # Support both `bill_no` and camelCase `billNo` to match the public endpoint.
        bill_no = self.request.query_params.get('bill_no') or self.request.query_params.get('billNo')
        if bill_no:
            bill_no = str(bill_no).strip()
            if bill_no:
                # Be resilient to case differences or accidental whitespace.
                queryset = queryset.filter(bill_no__iexact=bill_no)
        return queryset

class GetTransitPermitDetailAPIView(generics.RetrieveAPIView):
    serializer_class = EnaTransitPermitDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = EnaTransitPermitDetail.objects.all()
        return scope_by_profile_or_workflow(
            self.request.user,
            queryset,
            WORKFLOW_IDS['TRANSIT_PERMIT'],
            licensee_field='licensee_id'
        )


class PublicTransitPermitAPIView(generics.ListAPIView):
    """
    Public (no-auth) endpoint to fetch limited transit permit details.

    Intended for sharing a permit snapshot externally. This endpoint requires `bill_no`
    (or `billNo`) query param and will never return a full unfiltered list.
    """

    serializer_class = PublicTransitPermitDetailSerializer
    permission_classes = [AllowAny]
    authentication_classes = []

    def _get_bill_no(self):
        return (
            self.kwargs.get('bill_no')
            or self.request.query_params.get('bill_no')
            or self.request.query_params.get('billNo')
        )

    def get_queryset(self):
        bill_no = self._get_bill_no()
        if not bill_no:
            return EnaTransitPermitDetail.objects.none()
        return EnaTransitPermitDetail.objects.filter(bill_no=bill_no).order_by('-id')

    def list(self, request, *args, **kwargs):
        bill_no = self._get_bill_no()
        if not bill_no:
            return Response(
                {"detail": "bill_no query param is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().list(request, *args, **kwargs)


class PerformTransitPermitActionAPIView(views.APIView):
    """
    API endpoint to perform an action (PAY, APPROVE, REJECT) on a transit permit.
    Dynamically determines the next status based on the current status and the action
    by querying the WorkflowTransition table.
    """
    permission_classes = [IsAuthenticated]

    def _expand_license_aliases(self, value: str):
        normalized = str(value or '').strip()
        if not normalized:
            return []
        aliases = [normalized]
        if normalized.startswith('NLI/'):
            aliases.append(f"NA/{normalized[4:]}")
        elif normalized.startswith('NA/'):
            aliases.append(f"NLI/{normalized[3:]}")
        return aliases

    def _collect_user_scoped_license_ids(self, user):
        scoped = set()

        assignment = getattr(user, 'oic_assignment', None)
        if assignment:
            for raw in [
                getattr(assignment, 'licensee_id', ''),
                getattr(getattr(assignment, 'license', None), 'license_id', ''),
                getattr(getattr(assignment, 'approved_application', None), 'application_id', ''),
            ]:
                for alias in self._expand_license_aliases(raw):
                    scoped.add(alias)

        profile = getattr(user, 'supply_chain_profile', None)
        if profile:
            for alias in self._expand_license_aliases(getattr(profile, 'licensee_id', '')):
                scoped.add(alias)

        units = getattr(user, 'manufacturing_units', None)
        if units is not None:
            for raw in (
                units.exclude(licensee_id__isnull=True)
                .exclude(licensee_id='')
                .values_list('licensee_id', flat=True)
            ):
                for alias in self._expand_license_aliases(raw):
                    scoped.add(alias)

        return scoped

    def _resolve_wallet_license_candidates(self, raw_licensee_id: str):
        normalized = str(raw_licensee_id or '').strip()
        if not normalized:
            return []

        candidates = set(self._expand_license_aliases(normalized))

        try:
            from models.masters.license.models import License

            license_rows = License.objects.filter(is_active=True).filter(
                Q(license_id__in=list(candidates)) | Q(source_object_id__in=list(candidates))
            )
            for row in license_rows:
                for raw in [getattr(row, 'license_id', ''), getattr(row, 'source_object_id', '')]:
                    for alias in self._expand_license_aliases(raw):
                        candidates.add(alias)
        except Exception:
            pass

        return [c for c in candidates if c]

    def _refund_wallet_balances_for_rejection(self, user, permit, cancellation_reason=''):
        from models.transactional.payment.models import WalletBalance, WalletTransaction

        bill_no = str(getattr(permit, 'bill_no', '') or '').strip()
        if not bill_no:
            return {"credited": 0, "skipped": 0, "missing_wallet": 0}

        candidates = self._resolve_wallet_license_candidates(getattr(permit, 'licensee_id', ''))
        debit_qs = WalletTransaction.objects.filter(
            source_module='transit_permit',
            reference_no=bill_no,
            entry_type__iexact='DR',
        )
        if candidates:
            debit_qs = debit_qs.filter(licensee_id__in=candidates)

        debit_rows = list(
            debit_qs.select_related('wallet_balance').order_by('wallet_transaction_id')
        )
        if not debit_rows:
            return {"credited": 0, "skipped": 0, "missing_wallet": 0}

        now_ts = timezone.now()
        actor = str(getattr(user, 'username', '') or '')
        reason = str(cancellation_reason or '').strip()
        reason_suffix = f" Reason: {reason}" if reason else ""
        summary = {"credited": 0, "skipped": 0, "missing_wallet": 0}

        with transaction.atomic():
            for debit_row in debit_rows:
                amount = Decimal(str(debit_row.amount or 0))
                if amount <= 0:
                    summary["skipped"] += 1
                    continue

                refund_transaction_id = f"{debit_row.transaction_id}-REFUND"
                already_refunded = WalletTransaction.objects.filter(
                    transaction_id=refund_transaction_id,
                    source_module='transit_permit_refund',
                    reference_no=bill_no,
                    entry_type__iexact='CR',
                ).exists()
                if already_refunded:
                    summary["skipped"] += 1
                    continue

                wallet = (
                    WalletBalance.objects.select_for_update()
                    .filter(wallet_balance_id=debit_row.wallet_balance_id)
                    .first()
                )
                if not wallet:
                    summary["missing_wallet"] += 1
                    continue

                before = Decimal(str(wallet.current_balance or 0))
                after = before + amount
                wallet.current_balance = after
                wallet.total_credit = Decimal(str(wallet.total_credit or 0)) + amount
                wallet.last_updated_at = now_ts
                wallet.save(update_fields=['current_balance', 'total_credit', 'last_updated_at'])

                WalletTransaction.objects.create(
                    wallet_balance=wallet,
                    transaction_id=refund_transaction_id,
                    licensee_id=wallet.licensee_id or debit_row.licensee_id,
                    licensee_name=wallet.licensee_name or debit_row.licensee_name,
                    user_id=actor or wallet.user_id or debit_row.user_id,
                    module_type=wallet.module_type or debit_row.module_type,
                    wallet_type=wallet.wallet_type or debit_row.wallet_type,
                    head_of_account=wallet.head_of_account or debit_row.head_of_account,
                    entry_type='CR',
                    transaction_type='credit',
                    amount=amount,
                    balance_before=before,
                    balance_after=after,
                    reference_no=bill_no,
                    source_module='transit_permit_refund',
                    payment_status='refunded',
                    remarks=(f"Refund for cancelled transit permit {bill_no}.{reason_suffix}")[:300],
                    created_at=now_ts,
                )
                summary["credited"] += 1

        return summary

    def post(self, request, pk):
        try:
            action = str(request.data.get('action') or '').strip().upper()
            remarks = str(
                request.data.get('remarks')
                or request.data.get('comments')
                or ''
            ).strip()
            if not action:
                return Response({
                    'status': 'error',
                    'message': 'Action is required'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Get the transit permit
            permit = EnaTransitPermitDetail.objects.get(pk=pk)

            # Ownership/permission check (dynamic, DB-driven).
            # Workflow users (OIC/officers) can process mapped workflow items.
            # Licensee users can process only their own permit.
            permit_licensee_id = str(permit.licensee_id or '').strip()
            user_scoped_ids = self._collect_user_scoped_license_ids(request.user)
            permit_aliases = set(self._expand_license_aliases(permit_licensee_id))
            mapped_to_permit = bool(permit_aliases.intersection(user_scoped_ids))

            if has_workflow_access(request.user, WORKFLOW_IDS['TRANSIT_PERMIT']) and mapped_to_permit:
                pass
            elif hasattr(request.user, 'supply_chain_profile'):
                if not mapped_to_permit:
                    raise PermissionDenied("You are not allowed to modify this transit permit.")
            else:
                raise PermissionDenied("You are not allowed to modify this transit permit.")
            
            # --- Use WorkflowService to advance stage ---
            from auth.workflow.services import WorkflowService
            from auth.workflow.models import WorkflowStage
            
            # Ensure current_stage is set (if missing)
            if not permit.current_stage or not permit.workflow:
                 try:
                     from auth.workflow.models import Workflow
                     workflow_obj = Workflow.objects.get(id=WORKFLOW_IDS['TRANSIT_PERMIT'])
                     permit.workflow = workflow_obj
                     current_stage = self._resolve_stage_from_status_code(workflow_obj, permit.status_code)
                     if not current_stage:
                         current_stage = WorkflowStage.objects.filter(workflow=workflow_obj, is_initial=True).first()
                     if not current_stage:
                         raise WorkflowStage.DoesNotExist("Initial workflow stage not found")
                     permit.current_stage = current_stage
                     permit.status = current_stage.name
                     permit.save()
                 except (Workflow.DoesNotExist, WorkflowStage.DoesNotExist):
                      return Response({
                         'status': 'error',
                         'message': 'Workflow configuration not found. Please run "python manage.py populate_transit_permit_workflow".'
                     }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                 except Exception as e:
                     return Response({
                        'status': 'error',
                        'message': f"Database Error during workflow initialization: {str(e)}"
                     }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Extra check to be sure
            if not permit.current_stage:
                 return Response({
                    'status': 'error',
                    'message': 'Current Stage is Null. Workflow initialization failed.'
                 }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Context for validation
            context = {
                "action": action
            }

            transitions = WorkflowService.get_next_stages(permit)
            target_transition = None
            
            for t in transitions:
                if transition_matches(t, request.user, action):
                    target_transition = t
                    break

            if not target_transition:
                return Response({
                    'status': 'error',
                    'message': f'No valid transition for Action: {action} on Status: {permit.status}'
                }, status=status.HTTP_400_BAD_REQUEST)
                
            WorkflowService.advance_stage(
                application=permit,
                user=request.user,
                target_stage=target_transition.to_stage,
                context=context,
                remarks=remarks or f"Action: {action}"
            )
            
            # Sync back to status/status_code
            new_stage_name = target_transition.to_stage.name
            permit.status = new_stage_name
            # Keep status_code compatibility without relying on stage names.
            if target_transition.to_stage.is_initial:
                permit.status_code = 'TRP_01'
            elif action == 'PAY':
                permit.status_code = 'TRP_02'
            elif action == 'APPROVE':
                permit.status_code = 'TRP_03'
            elif action == 'REJECT':
                permit.status_code = 'TRP_04'
            
            permit.save()
            
            # Check for stock deduction trigger
            if action == 'PAY':
                # Wallet is already debited at submit time.
                # On PAY we only continue stock/workflow processing.
                self._handle_stock_deduction(permit, user=request.user)

            elif action == 'APPROVE':
                # Update utilization records with OIC's full name as approved_by
                self._update_utilization_approved_by(permit, request.user)

            elif action == 'REJECT':
                self._handle_rejection(request, permit, remarks=remarks)
            
            serializer = EnaTransitPermitDetailSerializer(permit)
            return Response({
                'status': 'success',
                'message': f'Transit Permit status updated to {new_stage_name}',
                'data': serializer.data
            }, status=status.HTTP_200_OK)

        except (PermissionDenied, DjangoPermissionDenied) as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            logger.exception(
                "Unhandled error while updating transit permit status (permit=%s)",
                getattr(locals().get("permit", None), "bill_no", None),
            )
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _handle_rejection(self, request, permit, remarks=''):
        cancellation_reason = str(
            remarks
            or request.data.get('remarks')
            or request.data.get('comments')
            or 'Rejected by OIC'
        ).strip()

        # 1. Refund wallet. This should not block cancellation-log creation.
        try:
            refund_summary = self._refund_wallet_balances_for_rejection(
                request.user,
                permit,
                cancellation_reason=cancellation_reason
            )
            logger.debug(
                "Wallet refund summary for %s -> credited=%s skipped=%s missing_wallet=%s",
                permit.bill_no,
                refund_summary.get("credited", 0),
                refund_summary.get("skipped", 0),
                refund_summary.get("missing_wallet", 0),
            )
        except Exception as wallet_error:
            logger.exception(
                "Wallet refund during rejection failed for permit=%s",
                getattr(permit, "bill_no", None),
            )

        # 2. Restore stock and insert cancellation rows.
        try:
            from models.transactional.supply_chain.brand_warehouse.models import (
                BrandWarehouse,
                BrandWarehouseUtilization,
                BrandWarehouseTpCancellation,
            )
            from django.db import connection as _db_conn

            # Reset sequence to avoid primary key conflicts from manual DB operations
            with _db_conn.cursor() as _cur:
                _cur.execute(
                    "SELECT setval(pg_get_serial_sequence('brand_warehouse_tp_cancellation', 'id'), "
                    "COALESCE((SELECT MAX(id) FROM brand_warehouse_tp_cancellation), 0) + 1, false)"
                )

            utilizations = BrandWarehouseUtilization.objects.filter(permit_no=permit.bill_no)
            if utilizations.exists():
                for utilization in utilizations:
                    warehouse = utilization.brand_warehouse
                    previous_stock = warehouse.current_stock

                    warehouse.current_stock += utilization.quantity
                    warehouse.save()
                    warehouse.update_status()
                    new_stock = warehouse.current_stock

                    utilization.status = 'CANCELLED'
                    utilization.save()

                    BrandWarehouseTpCancellation.objects.create(
                        brand_warehouse=warehouse,
                        reference_no=permit.bill_no,
                        cancelled_by=_get_user_display_name(request.user),
                        quantity_cases=utilization.cases,
                        quantity_bottles=utilization.total_bottles,
                        amount_refunded=permit.total_amount,
                        reason=cancellation_reason,
                        previous_stock=previous_stock,
                        new_stock=new_stock,
                        permit_date=utilization.date,
                        destination=utilization.distributor,
                        vehicle_no=utilization.vehicle,
                        depot_address=utilization.depot_address,
                        brand_name=f"{warehouse.brand_type} ({warehouse.capacity_size}ml)"
                    )
                return

            # Fallback: create cancellation rows from permit lines even when utilization rows are missing.
            logger.warning(
                "No utilization found for permit=%s; creating fallback cancellation entries",
                getattr(permit, "bill_no", None),
            )
            bill_items = EnaTransitPermitDetail.objects.filter(bill_no=permit.bill_no)
            created_count = 0

            for item in bill_items:
                item_license_id = str(item.licensee_id or '').strip()
                warehouse_qs = BrandWarehouse.objects.filter(capacity_size__size_ml=_get_size_ml_value(item))
                if item_license_id:
                    warehouse_qs = warehouse_qs.filter(license_id=item_license_id)

                warehouse = warehouse_qs.filter(brand__brand_name__iexact=item.brand).first()
                if not warehouse:
                    warehouse = warehouse_qs.filter(brand__brand_name__icontains=item.brand).first()
                if not warehouse:
                    continue

                BrandWarehouseTpCancellation.objects.create(
                    brand_warehouse=warehouse,
                    reference_no=permit.bill_no,
                    cancelled_by=_get_user_display_name(request.user),
                    quantity_cases=int(item.cases or 0),
                    quantity_bottles=int(item.cases or 0) * int(item.bottles_per_case or 0),
                    amount_refunded=item.total_amount,
                    reason=cancellation_reason,
                    previous_stock=warehouse.current_stock,
                    new_stock=warehouse.current_stock,
                    permit_date=item.date,
                    destination=item.sole_distributor_name,
                    vehicle_no=item.vehicle_number,
                    depot_address=item.depot_address,
                    brand_name=f"{item.brand} ({_get_size_ml_value(item)}ml)"
                )
                created_count += 1

            if created_count == 0:
                logger.warning(
                    "No brand_warehouse match found for fallback cancellation rows on permit=%s",
                    getattr(permit, "bill_no", None),
                )
            else:
                logger.info(
                    "Created %s fallback cancellation rows for permit=%s",
                    created_count,
                    getattr(permit, "bill_no", None),
                )
        except Exception as cancellation_error:
            logger.exception(
                "Error creating fallback cancellation rows for permit=%s",
                getattr(permit, "bill_no", None),
            )

    def _update_utilization_approved_by(self, permit, user):
        """Update utilization records with OIC's full name when they approve."""
        from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouseUtilization
        full_name = _get_user_display_name(user)
        BrandWarehouseUtilization.objects.filter(
            permit_no=permit.bill_no
        ).update(approved_by=full_name)

    def _handle_stock_deduction(self, permit, user=None):
        """
        Check if all items in the bill are paid, and if so, deduct stock from BrandWarehouse
        """
        try:
            # 1. Check if ALL items for this bill are paid
            bill_items = EnaTransitPermitDetail.objects.filter(bill_no=permit.bill_no)
            
            # defined paid status - simplistic check based on what we just set
            # Ideally use a list of "paid" statuses if workflow is complex
            # For now, we assume if we just set it to a "PaymentSuccessful..." status, others should match or be in advanced stages
            
            # Count items that are NOT in a paid/approved state
            # "Ready for Payment" is the state BEFORE payment. 
            unpaid_count = bill_items.filter(
                Q(current_stage__isnull=True) | Q(current_stage__is_initial=True)
            ).count()
            

            if unpaid_count == 0:
                # ALL items are paid. Trigger deduction for each.
                
                from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouse, BrandWarehouseUtilization
                
                for item in bill_items:
                    item_license_id = str(item.licensee_id or '').strip()

                    # Check if utilization already exists to prevent double deduction
                    utilization_qs = BrandWarehouseUtilization.objects.filter(
                        permit_no=item.bill_no,
                        brand_warehouse__brand__brand_name__iexact=item.brand,
                        brand_warehouse__capacity_size__size_ml=_get_size_ml_value(item),
                    )
                    if item_license_id:
                        utilization_qs = utilization_qs.filter(brand_warehouse__license_id=item_license_id)
                    if utilization_qs.exists():
                         continue

                    # Find matching BrandWarehouse entry
                    warehouse_qs = BrandWarehouse.objects.filter(capacity_size__size_ml=_get_size_ml_value(item))
                    if item_license_id:
                        warehouse_qs = warehouse_qs.filter(license_id=item_license_id)

                    warehouse_entry = warehouse_qs.filter(
                        brand__brand_name__iexact=item.brand
                    ).first()
                    
                    if not warehouse_entry:
                        warehouse_entry = warehouse_qs.filter(
                            brand__brand_name__icontains=item.brand,
                        ).first()
                        
                    if warehouse_entry:
                        logger.debug(
                            "Found warehouse entry %s for brand=%s (license_id=%s)",
                            warehouse_entry,
                            getattr(item, "brand", None),
                            item_license_id or "N/A",
                        )
                        
                        # Calculate quantity (pieces)
                        # We have item.cases. Need to convert to bottles/pieces if we store pieces in warehouse
                        # BrandWarehouse.current_stock is in UNTIS (pieces/bottles)
                        # We need bottles per case.
                        
                        # Get bottles per case from Master Table (BrandMlInCases)
                        from models.masters.supply_chain.transit_permit.models import BrandMlInCases
                        
                        bottles_per_case = int(getattr(item, 'bottles_per_case', 0) or 0)
                        
                        # Try to find specific configuration for this size
                        ml_config = BrandMlInCases.objects.filter(ml=int(warehouse_entry.capacity_size)).first()
                        if ml_config and ml_config.pieces_in_case:
                            bottles_per_case = int(ml_config.pieces_in_case)
                        else:
                            if bottles_per_case <= 0:
                                bottles_per_case = 1
                            logger.warning(
                                "No ML configuration found for %sml. Using fallback bottles_per_case=%s (permit/default).",
                                getattr(warehouse_entry, "capacity_size", None),
                                bottles_per_case,
                            )
                        
                        total_pieces = int(item.cases) * bottles_per_case
                        
                        # Create Utilization Record
                        # This auto-deducts from BrandWarehouse via the save() method in BrandWarehouseUtilization model
                        utilization = BrandWarehouseUtilization.objects.create(
                            brand_warehouse=warehouse_entry,
                            license_id=item_license_id or str(getattr(warehouse_entry, 'license_id', '') or '').strip() or None,
                            permit_no=item.bill_no,
                            date=item.date, # Date of permit
                            distributor=item.sole_distributor_name,
                            depot_address=item.depot_address,
                            vehicle=item.vehicle_number,
                            quantity=total_pieces, # Quantity in pieces
                            cases=item.cases,
                            bottles_per_case=bottles_per_case,
                            status='APPROVED', # Setting directly to APPROVED to trigger deduction
                            approved_by=_get_user_display_name(user) if user else 'System (Payment Auto-Deduction)',
                            approval_date=timezone.now()
                        )
                        
                    else:
                        logger.warning(
                            "No warehouse entry found for brand=%s size_ml=%s license_id=%s",
                            getattr(item, "brand", None),
                            getattr(item, "size_ml", None),
                            item_license_id or "N/A",
                        )
                        
            else:
                logger.debug(
                    "Stock deduction skipped for permit=%s (unpaid_count=%s)",
                    getattr(permit, "bill_no", None),
                    unpaid_count,
                )
                return

        except Exception as e:
            logger.exception(
                "Unhandled error during stock deduction for permit=%s",
                getattr(permit, "bill_no", None),
            )




    def _handle_wallet_deduction(self, user, permit):
        """
        Deduct the permit's financial amounts from the user's wallet.
        Raises exception if insufficient funds.
        """
        try:
            from .models import Wallet, WalletTransaction
            
            # 1. Get Wallet
            wallet = Wallet.objects.filter(user=user).first()
            if not wallet:
                wallet = Wallet.objects.create(
                    user=user,
                    excise_balance=10000000.00, # Default high balance for dev
                    additional_excise_balance=10000000.00,
                    education_cess_balance=10000000.00
                )
            
            # 2. Calculate Amounts for THIS permit item
            # Using float conversion to be safe, though Decimal is better
            excise_amount = float(permit.total_excise_duty or 0)
            additional_excise_amount = float(permit.total_additional_excise or 0)
            cess_amount = float(permit.total_education_cess or 0)
            
            total_required_excise = excise_amount
            total_required_additional = additional_excise_amount
            total_required_cess = cess_amount
            
            
            # 3. Check Balances
            if float(wallet.excise_balance) < total_required_excise:
                raise Exception(f"Insufficient Excise Wallet Balance. Available: {wallet.excise_balance}, Required: {total_required_excise}")
            
            if float(wallet.additional_excise_balance) < total_required_additional:
                 raise Exception(f"Insufficient Additional Excise Wallet Balance. Available: {wallet.additional_excise_balance}, Required: {total_required_additional}")
                 
            if float(wallet.education_cess_balance) < total_required_cess:
                raise Exception(f"Insufficient Education Cess Wallet Balance. Available: {wallet.education_cess_balance}, Required: {total_required_cess}")
                
            # 4. Deduct
            wallet.excise_balance = float(wallet.excise_balance) - total_required_excise
            wallet.additional_excise_balance = float(wallet.additional_excise_balance) - total_required_additional
            wallet.education_cess_balance = float(wallet.education_cess_balance) - total_required_cess
            wallet.save()
            
            # 5. Log Transactions
            if total_required_excise > 0:
                WalletTransaction.objects.create(
                    wallet=wallet, transaction_type='DEBIT', amount=total_required_excise, 
                    head='EXCISE', reference_no=permit.bill_no, description=f'Payment for Permit Item {permit.id}'
                )
            if total_required_additional > 0:
                WalletTransaction.objects.create(
                    wallet=wallet, transaction_type='DEBIT', amount=total_required_additional, 
                    head='ADDITIONAL_EXCISE', reference_no=permit.bill_no, description=f'Payment for Permit Item {permit.id}'
                )
            if total_required_cess > 0:
                WalletTransaction.objects.create(
                    wallet=wallet, transaction_type='DEBIT', amount=total_required_cess, 
                    head='EDUCATION_CESS', reference_no=permit.bill_no, description=f'Payment for Permit Item {permit.id}'
                )
                

        except Exception as e:
            raise e # Re-raise to stop the transaction/response
