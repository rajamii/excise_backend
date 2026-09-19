from rest_framework import serializers
from .models import NewLicenseApplication, Transaction, Objection
from auth.user.models import CustomUser
from auth.roles.models import Role
from auth.workflow.serializers import WorkflowTransactionSerializer, WorkflowObjectionSerializer
from models.masters.core.models import (
    District,
    Subdivision,
    PoliceStation,
    LicenseCategory,
    LicenseSubcategory,
    LicenseType,
    Road,
    LicenseFee,
    Location,
)
from utils.fields import CodeRelatedField
from . import helpers

from decimal import Decimal


PACHWAI_MODULE_CODE = "NLI_ADD_PACHWAI"
DRAUGHT_BEER_MODULE_CODE = "NLI_ADD_DRAUGHT_BEER"
MINI_BAR_MODULE_CODE = "NLI_ADD_MINI_BAR"


def _get_additional_charge_details(obj: NewLicenseApplication):
    """
    Returns (breakdown_list, total_decimal) for all active additional charges on this application.
    """
    breakdown = []
    total = Decimal("0.00")
    try:
        from models.masters.core.models import MasterFixedFee

        module_fees = {
            m["fee_code"]: (m["amount"] if m["amount"] is not None else Decimal("0.00"))
            for m in MasterFixedFee.objects.filter(
                fee_code__in=[PACHWAI_MODULE_CODE, DRAUGHT_BEER_MODULE_CODE, MINI_BAR_MODULE_CODE],
                is_active=True,
            ).values("fee_code", "amount")
        }
        if getattr(obj, "pachwai", False):
            amt = module_fees.get(PACHWAI_MODULE_CODE, Decimal("3000.00"))
            total += amt
            breakdown.append({
                "code": "pachwai",
                "label": "Pachwai (Additional)",
                "unit_amount": float(amt),
                "quantity": 1,
                "amount": float(amt),
            })
        if getattr(obj, "draught_beer", False):
            amt = module_fees.get(DRAUGHT_BEER_MODULE_CODE, Decimal("5000.00"))
            total += amt
            breakdown.append({
                "code": "draught_beer",
                "label": "Draught Beer (Additional)",
                "unit_amount": float(amt),
                "quantity": 1,
                "amount": float(amt),
            })
        if getattr(obj, "mini_bar", False):
            qty = getattr(obj, "mini_bar_quantity", 0) or 0
            if qty < 1:
                qty = 1
            unit_amt = module_fees.get(MINI_BAR_MODULE_CODE, Decimal("1000.00"))
            amt = unit_amt * Decimal(str(qty))
            total += amt
            breakdown.append({
                "code": "mini_bar",
                "label": f"Mini Bar (Additional x{qty})",
                "unit_amount": float(unit_amt),
                "quantity": qty,
                "amount": float(amt),
            })
    except Exception:
        pass
    return breakdown, total


def _get_additional_charge_total(obj: NewLicenseApplication) -> Decimal:
    _, total = _get_additional_charge_details(obj)
    return total


class UserShortSerializer(serializers.ModelSerializer):
    role_id = serializers.IntegerField(source='role.id', read_only=True)
    
    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'role', 'role_id']

class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ['id', 'name']

class ResolveObjectionSerializer(serializers.ModelSerializer):
    site_district = CodeRelatedField(
        queryset=District.objects.all(), lookup_field='district_code', required=False
    )
    site_subdivision = CodeRelatedField(
        queryset=Subdivision.objects.all(), lookup_field='subdivision_code', required=False
    )
    road = CodeRelatedField(
        queryset=Road.objects.all(), lookup_field='road', required=False
    )
    police_station = CodeRelatedField(
        queryset=PoliceStation.objects.all(), lookup_field='police_station_code', required=False
    )

    class Meta:
        model = NewLicenseApplication
        fields = '__all__'  # or limit to only fields needed in objection resolution

class TransactionSerializer(serializers.ModelSerializer):
    performed_by = UserShortSerializer(read_only=True)
    forwarded_by = RoleSerializer(read_only=True)
    forwarded_to = RoleSerializer(source='forwarded_to.name', read_only=True)
    
    class Meta:
        model = Transaction
        fields = ['license_application', 'stage', 'remarks', 'timestamp', 'performed_by', 'forwarded_by', 'forwarded_to']

class ObjectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Objection
        fields = '__all__'


class NewLicenseApplicationSerializer(serializers.ModelSerializer):
    # Salesman/Barman details captured during new license flow (stored in salesman_barman_application)
    member_name = serializers.CharField(required=False, allow_blank=True, allow_null=True, write_only=True)
    member_father_husband_name = serializers.CharField(required=False, allow_blank=True, allow_null=True, write_only=True)
    member_gender = serializers.CharField(required=False, allow_blank=True, allow_null=True, write_only=True)
    member_dob = serializers.DateField(required=False, allow_null=True, write_only=True)
    member_nationality = serializers.CharField(required=False, allow_blank=True, allow_null=True, write_only=True)
    member_address = serializers.CharField(required=False, allow_blank=True, allow_null=True, write_only=True)
    member_pan = serializers.CharField(required=False, allow_blank=True, allow_null=True, write_only=True)
    member_mobile_number = serializers.CharField(required=False, allow_blank=True, allow_null=True, write_only=True)
    member_email = serializers.EmailField(required=False, allow_blank=True, allow_null=True, write_only=True)
    aadhaar = serializers.CharField(required=False, allow_blank=True, allow_null=True, write_only=True)
    sikkim_subject = serializers.BooleanField(required=False, allow_null=True, write_only=True)

    member_pass_photo = serializers.FileField(required=False, allow_null=True, write_only=True)
    member_aadhaar_card = serializers.FileField(required=False, allow_null=True, write_only=True)
    member_residential_certificate = serializers.FileField(required=False, allow_null=True, write_only=True)
    member_dob_proof = serializers.FileField(required=False, allow_null=True, write_only=True)
    
    # Code-based lookups
    site_district = CodeRelatedField(queryset=District.objects.all(), lookup_field='district_code')
    site_subdivision = CodeRelatedField(queryset=Subdivision.objects.all(), lookup_field='subdivision_code')
    police_station = CodeRelatedField(queryset=PoliceStation.objects.all(), lookup_field='police_station_code')
    license_type = serializers.PrimaryKeyRelatedField(queryset=LicenseType.objects.all())
    license_category = serializers.PrimaryKeyRelatedField(queryset=LicenseCategory.objects.all())
    license_sub_category = serializers.PrimaryKeyRelatedField(queryset=LicenseSubcategory.objects.all())

    # Read-only display fields
    license_type_name = serializers.CharField(source='license_type.license_type', read_only=True)
    license_category_name = serializers.CharField(source='license_category.license_category', read_only=True)
    license_sub_category_name = serializers.CharField(source='license_sub_category.description', read_only=True)
    site_district_name = serializers.CharField(source='site_district.district', read_only=True)
    site_subdivision_name = serializers.CharField(source='site_subdivision.subdivision', read_only=True)
    police_station_name = serializers.CharField(source='police_station.police_station', read_only=True)
    current_stage_name = serializers.CharField(source='current_stage.name', read_only=True)

    renewal_of_license_id = serializers.CharField(source='renewal_of.license_id', read_only=True)
    transactions = WorkflowTransactionSerializer(many=True, read_only=True)
    objections = WorkflowObjectionSerializer(many=True, read_only=True)

    # Application fee payment status (BillDesk module_code=001) – annotated in views.
    application_fee_payment_status = serializers.CharField(read_only=True, allow_blank=True, allow_null=True)
    application_fee_transaction_id = serializers.CharField(read_only=True, allow_blank=True, allow_null=True)
    application_fee_payment_date = serializers.DateTimeField(read_only=True, allow_null=True)
    application_fee_error = serializers.CharField(read_only=True, allow_blank=True, allow_null=True)

    # Site enquiry revert badge (annotated in views).
    site_enquiry_is_reverted = serializers.BooleanField(read_only=True, default=False)
    site_enquiry_reverted_remarks = serializers.CharField(read_only=True, allow_blank=True, allow_null=True)

    # Commissioner revert remarks
    commissioner_revert_remarks = serializers.SerializerMethodField()
    is_reverted_by_commissioner = serializers.SerializerMethodField()
    latest_revert = serializers.SerializerMethodField()

    # Backward-compatible fee field used across multiple frontend screens.
    yearly_license_fee = serializers.SerializerMethodField()
    license_fee_amount = serializers.SerializerMethodField()
    security_fee_amount = serializers.SerializerMethodField()
    base_license_fee = serializers.SerializerMethodField()
    base_security_fee = serializers.SerializerMethodField()
    additional_charges_total = serializers.SerializerMethodField()
    additional_charges_breakdown = serializers.SerializerMethodField()
    valid_up_to = serializers.SerializerMethodField()
    issued_license_id = serializers.SerializerMethodField()
    renewal_application_id = serializers.SerializerMethodField()
    # Countdown Timer Fields
    payment_deadline_at = serializers.SerializerMethodField()
    is_payment_timer_active = serializers.SerializerMethodField()
    payment_time_remaining_seconds = serializers.SerializerMethodField()
    objection_deadline_at = serializers.SerializerMethodField()
    is_objection_timer_active = serializers.SerializerMethodField()
    objection_time_remaining_seconds = serializers.SerializerMethodField()
    # Rejection Reason & Note Fields
    rejection_reason = serializers.SerializerMethodField()
    is_auto_rejected = serializers.SerializerMethodField()

    class Meta:
        model = NewLicenseApplication
        fields = '__all__'
        read_only_fields = [
            'application_id',
            'current_stage',
            'is_approved',
            'created_at',
            'updated_at',
            'applicant',
            'workflow',
            'is_application_fee_paid',
        ]

    def _resolve_license_fee(self, obj) -> LicenseFee | None:
        fee_id = getattr(obj, "licensee_fee_id", None)
        if fee_id:
            try:
                fee = LicenseFee.objects.filter(id=int(fee_id), is_active=True).first()
                if fee:
                    return fee
            except Exception:
                pass

        # Fallback: resolve fee row from category/subcategory (+ location when available).
        # Some deployments store `licensee_fee_id` only after commissioner approval; for
        # awaiting-payment screens we still need to show the configured amounts.
        try:
            cat_id = getattr(obj, "license_category_id", None)
            scat_id = getattr(obj, "license_sub_category_id", None)
            if not cat_id or not scat_id:
                return None

            district_code = None
            try:
                district_code = getattr(getattr(obj, "site_district", None), "district_code", None)
            except Exception:
                district_code = None

            location_code = None
            if district_code is not None:
                location = (
                    Location.objects.filter(district_code=district_code, is_active=True)
                    .order_by("location_code")
                    .first()
                )
                location_code = getattr(location, "location_code", None) if location else None

            qs = LicenseFee.objects.filter(is_active=True)

            # Prefer direct FK-id match.
            direct = qs.filter(
                license_category_id=int(cat_id),
                license_subcategory_id=int(scat_id),
            )
            if location_code is not None:
                direct = direct.filter(location_code_id=int(location_code))
            fee = direct.order_by("id").first()
            if fee:
                return fee

            # Fallback: some deployments keep fee rows without location_code.
            # Try again without location constraint.
            fee = qs.filter(
                license_category_id=int(cat_id),
                license_subcategory_id=int(scat_id),
            ).order_by("id").first()
            if fee:
                return fee

            # Fallback: match by legacy codes stored on masters.
            category = getattr(obj, "license_category", None)
            subcategory = getattr(obj, "license_sub_category", None)
            cat_code = getattr(category, "old_license_cat_code", None)
            scat_code = getattr(subcategory, "old_license_scat_code", None)
            if cat_code is None or scat_code is None:
                return None

            legacy = qs.filter(
                license_category__old_license_cat_code=int(cat_code),
                license_subcategory__old_license_scat_code=int(scat_code),
            )
            if location_code is not None:
                legacy = legacy.filter(location_code_id=int(location_code))
            fee = legacy.order_by("id").first()
            if fee:
                return fee

            # Fallback: try legacy match without location constraint.
            return qs.filter(
                license_category__old_license_cat_code=int(cat_code),
                license_subcategory__old_license_scat_code=int(scat_code),
            ).order_by("id").first()
        except Exception:
            return None

    def get_yearly_license_fee(self, obj):
        fee = self._resolve_license_fee(obj)
        if not fee:
            return ""
        try:
            base = getattr(fee, "license_fee", None)
            if base is None:
                return ""
            return str(base + _get_additional_charge_total(obj))
        except Exception:
            return ""

    def get_license_fee_amount(self, obj):
        fee = self._resolve_license_fee(obj)
        base = getattr(fee, "license_fee", None) if fee else None
        if base is None:
            return None
        return base + _get_additional_charge_total(obj)

    def get_security_fee_amount(self, obj):
        fee = self._resolve_license_fee(obj)
        base = getattr(fee, "security_amount", None) if fee else None
        if base is None:
            return None
        return base + _get_additional_charge_total(obj)

    def get_base_license_fee(self, obj):
        fee = self._resolve_license_fee(obj)
        base = getattr(fee, "license_fee", None) if fee else None
        return float(base) if base is not None else None

    def get_base_security_fee(self, obj):
        fee = self._resolve_license_fee(obj)
        base = getattr(fee, "security_amount", None) if fee else None
        return float(base) if base is not None else None

    def get_additional_charges_total(self, obj):
        total = _get_additional_charge_total(obj)
        return float(total) if total is not None else 0.0

    def get_additional_charges_breakdown(self, obj):
        breakdown, _ = _get_additional_charge_details(obj)
        return breakdown

    def validate(self, data):
        # Resolve-objection updates are partial payloads, so only validate fields that
        # are actually being updated in this request.
        license_type = data.get('license_type') or getattr(self.instance, 'license_type', None)
        is_company = False
        if license_type:
            is_company = license_type.license_type.lower() == 'company' or license_type.id == 2

        if not is_company:
            if 'mobile_number' in data and data['mobile_number']:
                helpers.validate_mobile_number(data['mobile_number'])
            if 'email' in data and data['email']:
                helpers.validate_email_field(data['email'])
        
        if 'pan' in data and data['pan']:
            helpers.validate_pan_number(data['pan'])

        if is_company:
            # Set individual-only personal details to None/null for Company applications
            individual_only_fields = [
                'applicant_name', 'father_husband_name', 'dob', 'gender',
                'residential_status', 'marital_status', 'has_sikkim_certificate', 'has_excise_license',
                'family_excise_license', 'criminal_conviction', 'coi_rc_ss',
                'pass_photo', 'dob_proof', 'sikkim_certificate',
                'email', 'mobile_number'
            ]
            for field in individual_only_fields:
                if field in data or self.instance is None:
                    data[field] = None

        if data.get('company_gst'):
            helpers.validate_gst_number(data['company_gst'])
        if data.get('company_email'):
            helpers.validate_email_field(data['company_email'])
        if data.get('company_phone_number'):
            helpers.validate_mobile_number(data['company_phone_number'])
        if 'pin_code' in data:
            helpers.validate_pin_code(data['pin_code'])
        return data

    def create(self, validated_data):
        # Extract salesman/barman draft details before creating the new license application
        member_payload = {
            "member_name": validated_data.pop("member_name", None),
            "member_father_husband_name": validated_data.pop("member_father_husband_name", None),
            "member_gender": validated_data.pop("member_gender", None),
            "member_dob": validated_data.pop("member_dob", None),
            "member_nationality": validated_data.pop("member_nationality", None),
            "member_address": validated_data.pop("member_address", None),
            "member_pan": validated_data.pop("member_pan", None),
            "member_mobile_number": validated_data.pop("member_mobile_number", None),
            "member_email": validated_data.pop("member_email", None),
            "aadhaar": validated_data.pop("aadhaar", None),
            "sikkim_subject": validated_data.pop("sikkim_subject", None),
            "member_pass_photo": validated_data.pop("member_pass_photo", None),
            "member_aadhaar_card": validated_data.pop("member_aadhaar_card", None),
            "member_residential_certificate": validated_data.pop("member_residential_certificate", None),
            "member_dob_proof": validated_data.pop("member_dob_proof", None),
        }

        application = super().create(validated_data)

        # Store the member payload on the instance so the view can create the
        # SalesmanBarmanModel record AFTER the NLI transaction commits (in its own
        # separate transaction). Doing it here inside the NLI atomic block caused
        # nested transaction.atomic() calls in SalesmanBarmanModel.generate_application_id()
        # to abort the outer transaction on any failure, rolling back the NLI save too.
        application._member_payload = member_payload

        return application

    def get_valid_up_to(self, obj):
        try:
            from django.contrib.contenttypes.models import ContentType
            from models.masters.license.models import License
            ct = ContentType.objects.get_for_model(obj)
            license_obj = License.objects.filter(source_content_type=ct, source_object_id=obj.pk).first()
            if license_obj and license_obj.valid_up_to:
                return license_obj.valid_up_to.isoformat()
        except Exception:
            pass
        return None

    def get_issued_license_id(self, obj):
        try:
            from django.contrib.contenttypes.models import ContentType
            from models.masters.license.models import License
            ct = ContentType.objects.get_for_model(obj)
            license_obj = License.objects.filter(source_content_type=ct, source_object_id=obj.pk).first()
            if license_obj:
                return license_obj.license_id
        except Exception:
            pass
        return None

    def get_renewal_application_id(self, obj):
        try:
            from django.contrib.contenttypes.models import ContentType
            from models.masters.license.models import License
            from models.transactional.license_renewal_application.models import LicenseApplication
            
            ct = ContentType.objects.get_for_model(obj)
            license_obj = License.objects.filter(source_content_type=ct, source_object_id=obj.pk).first()
            if license_obj:
                renewal = LicenseApplication.objects.filter(old_license_id=license_obj.license_id).order_by('-created_at').first()
                if renewal:
                    return renewal.application_id
        except Exception:
            pass
        return None

    def get_commissioner_revert_remarks(self, obj) -> str | None:
        try:
            from auth.workflow.models import Revert
            from django.contrib.contenttypes.models import ContentType
            ct = ContentType.objects.get_for_model(obj)
            last_revert = Revert.objects.filter(content_type=ct, object_id=str(obj.pk)).order_by('-reverted_on').first()
            if last_revert:
                return last_revert.remarks
        except Exception:
            pass
        return None

    def get_is_reverted_by_commissioner(self, obj) -> bool:
        return self.get_commissioner_revert_remarks(obj) is not None

    def get_latest_revert(self, obj) -> dict | None:
        try:
            from auth.workflow.models import Revert
            from django.contrib.contenttypes.models import ContentType
            ct = ContentType.objects.get_for_model(obj)
            last_revert = Revert.objects.filter(content_type=ct, object_id=str(obj.pk)).order_by('-reverted_on').first()
            if last_revert:
                return {
                    "remarks": last_revert.remarks,
                    "reverted_by": f"{last_revert.reverted_by.first_name} {last_revert.reverted_by.last_name}".strip() if last_revert.reverted_by else "Unknown",
                    "reverted_by_role": last_revert.reverted_by.role.name if last_revert.reverted_by and last_revert.reverted_by.role else "Unknown",
                    "reverted_on": last_revert.reverted_on.isoformat()
                }
        except Exception:
            pass
    def get_is_payment_timer_active(self, obj) -> bool:
        if getattr(obj, "is_approved", False):
            return False
        stage_name = str(getattr(getattr(obj, "current_stage", None), "name", "") or "").lower()
        if "reject" in stage_name:
            return False
        stage_id = getattr(getattr(obj, "current_stage", None), "id", None)
        is_stage_23 = stage_id == 23 or "awaiting_payment" in stage_name or ("awaiting" in stage_name and "payment" in stage_name)
        if not is_stage_23:
            return False
        lic_paid = bool(getattr(obj, "is_license_fee_paid", False))
        sec_paid = bool(getattr(obj, "is_security_fee_paid", False))
        return not (lic_paid and sec_paid)

    def get_payment_deadline_at(self, obj):
        deadline = getattr(obj, "payment_deadline_at", None)
        if deadline:
            return deadline.isoformat() if hasattr(deadline, "isoformat") else str(deadline)
        if self.get_is_payment_timer_active(obj):
            try:
                from auth.workflow.services import WorkflowService
                entered_at = getattr(obj, "awaiting_payment_entered_at", None) or getattr(obj, "updated_at", None)
                d = WorkflowService._compute_new_license_payment_deadline(from_time=entered_at)
                return d.isoformat() if d else None
            except Exception:
                pass
        return None

    def get_payment_time_remaining_seconds(self, obj):
        if not self.get_is_payment_timer_active(obj):
            return None
        deadline_str = self.get_payment_deadline_at(obj)
        if not deadline_str:
            return None
        try:
            from django.utils import timezone
            from django.utils.dateparse import parse_datetime
            if isinstance(deadline_str, str):
                d = parse_datetime(deadline_str)
            else:
                d = deadline_str
            if not d:
                return None
            if timezone.is_naive(d):
                d = timezone.make_aware(d)
            now = timezone.now()
            diff = (d - now).total_seconds()
            return max(0, int(diff))
        except Exception:
            return None

    def _get_unresolved_objections(self, obj):
        try:
            from auth.workflow.models import Objection
            from django.contrib.contenttypes.models import ContentType
            ct = ContentType.objects.get_for_model(obj)
            return Objection.objects.filter(content_type=ct, object_id=str(obj.pk), is_resolved=False)
        except Exception:
            return []

    def get_is_objection_timer_active(self, obj) -> bool:
        if getattr(obj, "is_approved", False):
            return False
        stage_name = str(getattr(getattr(obj, "current_stage", None), "name", "") or "").lower()
        if "reject" in stage_name:
            return False
        if "objection" in stage_name:
            return True
        unresolved = self._get_unresolved_objections(obj)
        return any(bool(getattr(o, "deadline_at", None)) for o in unresolved)

    def get_objection_deadline_at(self, obj):
        if not self.get_is_objection_timer_active(obj):
            return None
        unresolved = self._get_unresolved_objections(obj)
        deadlines = [o.deadline_at for o in unresolved if getattr(o, "deadline_at", None)]
        if deadlines:
            earliest = min(deadlines)
            return earliest.isoformat() if hasattr(earliest, "isoformat") else str(earliest)
        # Fallback if in objection stage
        try:
            from auth.workflow.services import WorkflowService
            d = WorkflowService._compute_objection_deadline(from_time=getattr(obj, "updated_at", None))
            return d.isoformat() if d else None
        except Exception:
            return None

    def get_objection_time_remaining_seconds(self, obj):
        if not self.get_is_objection_timer_active(obj):
            return None
        deadline_str = self.get_objection_deadline_at(obj)
        if not deadline_str:
            return None
        try:
            from django.utils import timezone
            from django.utils.dateparse import parse_datetime
            if isinstance(deadline_str, str):
                d = parse_datetime(deadline_str)
            else:
                d = deadline_str
            if not d:
                return None
            if timezone.is_naive(d):
                d = timezone.make_aware(d)
            now = timezone.now()
            diff = (d - now).total_seconds()
            return max(0, int(diff))
        except Exception:
            return None

    def get_rejection_reason(self, obj):
        stage = getattr(obj, 'current_stage', None)
        stage_name = str(getattr(stage, 'name', '') or '').strip()
        stage_id = getattr(stage, 'id', None)
        stage_lower = stage_name.lower()

        # Check explicit timer-based auto-rejection stages
        if stage_id == 180 or ('payment' in stage_lower and 'reject' in stage_lower):
            return "Application automatically rejected: Required License Fee and Security Deposit payments were not completed within the configured payment deadline."
        
        if stage_id == 166 or ('objection' in stage_lower and 'reject' in stage_lower):
            return "Application automatically rejected: No action or clarification was submitted on the raised objection within the allowed time limit."

        # Check explicit Rejection entry in database
        try:
            from django.contrib.contenttypes.models import ContentType
            from auth.workflow.models import Rejection as RejectionModel
            ct = ContentType.objects.get_for_model(obj)
            rej = RejectionModel.objects.filter(content_type=ct, object_id=str(obj.pk)).order_by('-rejected_on').first()
            if rej and rej.remarks:
                return rej.remarks
        except Exception:
            pass

        # Check Workflow Transaction remarks
        try:
            from django.contrib.contenttypes.models import ContentType
            from auth.workflow.models import Transaction as WorkflowTransaction
            ct = ContentType.objects.get_for_model(obj)
            tx = WorkflowTransaction.objects.filter(
                content_type=ct,
                object_id=str(obj.pk),
                stage__name__icontains="reject"
            ).order_by('-timestamp').first()
            if tx and tx.remarks:
                return tx.remarks
        except Exception:
            pass

        if 'reject' in stage_lower:
            return f"Application was rejected at stage: {stage_name}"

        return None

    def get_is_auto_rejected(self, obj):
        stage = getattr(obj, 'current_stage', None)
        stage_name = str(getattr(stage, 'name', '') or '').strip()
        stage_id = getattr(stage, 'id', None)
        stage_lower = stage_name.lower()
        if stage_id in (166, 180) or ('reject' in stage_lower and ('no action' in stage_lower or 'payment' in stage_lower or 'objection' in stage_lower)):
            return True
        return False

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        cat = getattr(instance, 'license_category', None)
        if cat:
            rep['isSpecialPermitAllowed'] = getattr(cat, 'is_special_permit_allowed', False)
            rep['is_special_permit_allowed'] = getattr(cat, 'is_special_permit_allowed', False)
            rep['isDistributorUser'] = getattr(cat, 'is_distributor_user', False)
            rep['is_distributor_user'] = getattr(cat, 'is_distributor_user', False)
        return rep
