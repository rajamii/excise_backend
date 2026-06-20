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


def _get_additional_charge_total(obj: NewLicenseApplication) -> Decimal:
    """
    Additional charges are configurable in `masters_fixedfee` (MasterFixedFee.amount).
    They are added to both license fee and security fee when selected by the applicant.
    """
    total = Decimal("0.00")
    try:
        from models.masters.core.models import MasterFixedFee

        module_fees = {
            m["fee_code"]: (m["amount"] if m["amount"] is not None else Decimal("0.00"))
            for m in MasterFixedFee.objects.filter(
                fee_code__in=[PACHWAI_MODULE_CODE, DRAUGHT_BEER_MODULE_CODE],
                is_active=True,
            ).values("fee_code", "amount")
        }
        if getattr(obj, "pachwai", False):
            total += module_fees.get(PACHWAI_MODULE_CODE, Decimal("0.00"))
        if getattr(obj, "draught_beer", False):
            total += module_fees.get(DRAUGHT_BEER_MODULE_CODE, Decimal("0.00"))
    except Exception:
        # Non-blocking: if the master table isn't configured in a deployment, fall back to 0.
        pass
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

    # Backward-compatible fee field used across multiple frontend screens.
    yearly_license_fee = serializers.SerializerMethodField()
    license_fee_amount = serializers.SerializerMethodField()
    security_fee_amount = serializers.SerializerMethodField()
    valid_up_to = serializers.SerializerMethodField()
    issued_license_id = serializers.SerializerMethodField()
    renewal_application_id = serializers.SerializerMethodField()

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
