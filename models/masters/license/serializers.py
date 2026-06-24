from rest_framework import serializers
from .models import License
from auth.user.models import CustomUser
from django.utils import timezone
from datetime import timedelta
from models.masters.core.models import SupplyChainTimerConfig


class LicenseSerializer(serializers.ModelSerializer):
    license_category_name = serializers.CharField(source='license_category.license_category', read_only=True)
    license_sub_category_name = serializers.CharField(source='license_sub_category.description', read_only=True)
    excise_district_name = serializers.CharField(source='excise_district.district', read_only=True)
    source_type_display = serializers.CharField(source='get_source_type_display', read_only=True)

    class Meta:
        model = License
        fields = [
            'license_id',
            'source_type',
            'source_type_display',
            'license_category',
            'license_category_name',
            'license_sub_category',
            'license_sub_category_name',
            'excise_district',
            'excise_district_name',
            'issue_date',
            'valid_up_to',
            'is_active',
            'print_count',
            'is_print_fee_paid',
        ]


class LicenseDetailSerializer(serializers.ModelSerializer):
    license_category_name = serializers.CharField(source='license_category.license_category', read_only=True)
    license_sub_category_name = serializers.CharField(source='license_sub_category.description', read_only=True)
    excise_district_name = serializers.CharField(source='excise_district.district', read_only=True)
    issue_date = serializers.DateTimeField(format="%d/%m/%Y %H:%M:%S")
    valid_up_to = serializers.DateTimeField(format="%d/%m/%Y %H:%M:%S")

    source_type_display = serializers.CharField(source='get_source_type_display', read_only=True)
    source_application_id = serializers.CharField(source='source_application.application_id', read_only=True)

    application_data = serializers.SerializerMethodField()

    class Meta:
        model = License
        fields = [
            'license_id',
            'source_type_display',
            'source_application_id',
            'license_category_name',
            'license_sub_category_name',
            'excise_district_name',
            'issue_date',
            'valid_up_to',
            'is_active',
            'print_count',
            'is_print_fee_paid',
            'application_data',
        ]

    def get_application_data(self, obj):
        source = obj.source_application
        if not source:
            return {}

        # NEW LICENSE APPLICATION (NA)
        if obj.source_type == 'new_license_application':
            return {
                "applicant_name": source.applicant_name,
                "father_husband_name": source.father_husband_name,
                "dob": source.dob,
                "gender": source.get_gender_display() if hasattr(source, 'get_gender_display') else source.gender,
                "mobile_number": source.mobile_number,
                "email": source.email,
                "pan": source.pan,
                "address": source.present_address,
                "establishment_name": source.establishment_name,
                "site_district": source.site_district.district,
                "site_subdivision": source.site_subdivision.subdivision,
                "police_station": source.police_station.police_station,
                "license_type": source.license_type.license_type,
                "license_sub_category": source.license_sub_category.description,
                "mode_of_operation": source.get_mode_of_operation_display(),
            }

        # RENEWAL / EXISTING LICENSE (LA)
        elif obj.source_type == 'license_application':
            # Use the actual field names from your LicenseApplication model
            return {
                # "establishment_name": source.establishment_name,
                "licensee_name": source.establishment_name,  # often same
                "mobile_number": source.mobile_number,
                "email": source.email,
                "license_no": source.license_no,
                "initial_grant_date": source.initial_grant_date,
                "business_address": source.business_address or source.site_address,
                "police_station": source.police_station.police_station if source.police_station else None,
                "license_nature": source.license_nature,
                "functioning_status": source.functioning_status,
                "yearly_license_fee": source.yearly_license_fee,
                "license_type": source.license_type.license_type if hasattr(source, 'license_type') else None,
            }

        # SALESMAN / BARMAN (SB)
        elif obj.source_type == 'salesman_barman':
            full_name = " ".join(filter(None, [
                source.firstName,
                source.middleName or "",
                source.lastName
            ])).strip()

            return {
                "role": source.get_role_display(),
                "name": full_name,
                "father_husband_name": source.fatherHusbandName,
                "dob": source.dob,
                "gender": source.get_gender_display(),
                "address": source.address,
                "mobile_number": source.mobileNumber,
                "email": source.emailId or "",
                "pan": source.pan,
                "aadhaar": source.aadhaar,
                "sikkim_subject": source.sikkimSubject,
                "attached_license": source.license.license_id,
            }

        return {}

class MyLicenseDetailsSerializer(serializers.ModelSerializer):
    """Includes source application fee flags so the licensee UI can hide supply-chain menus until fee payment."""

    source_object_id = serializers.CharField(read_only=True)
    is_approved = serializers.SerializerMethodField()
    is_license_fee_paid = serializers.SerializerMethodField()
    is_security_fee_paid = serializers.SerializerMethodField()
    issue_date = serializers.SerializerMethodField()
    valid_up_to = serializers.SerializerMethodField()
    issue_date_display = serializers.SerializerMethodField()
    valid_up_to_display = serializers.SerializerMethodField()
    is_expired = serializers.SerializerMethodField()
    is_valid_now = serializers.SerializerMethodField()
    can_access_supply_chain = serializers.SerializerMethodField()
    can_renew = serializers.SerializerMethodField()
    renewal_window_starts_on = serializers.SerializerMethodField()
    renewal_window_ends_on = serializers.SerializerMethodField()
    reminder_window_days = serializers.SerializerMethodField()
    renewal_count = serializers.SerializerMethodField()
    renewal_details = serializers.SerializerMethodField()

    first_name = serializers.CharField(source='source_application.applicant.first_name', read_only=True)
    middle_name = serializers.CharField(source='source_application.applicant.middle_name', read_only=True)
    last_name = serializers.CharField(source='source_application.applicant.last_name', read_only=True)
    username = serializers.CharField(source='source_application.applicant.username', read_only=True)
    email = serializers.CharField(source='source_application.applicant.email', read_only=True)
    phone_number = serializers.CharField(source='source_application.applicant.phone_number', read_only=True)
    role = serializers.CharField(source='source_application.applicant.role', read_only=True)
    district = serializers.CharField(source='source_application.applicant.district.district', read_only=True)
    
    application_type = serializers.CharField(source='get_source_type_display', read_only=True)
    license_category = serializers.CharField(source='license_category.license_category', read_only=True)
    license_sub_category_id = serializers.IntegerField(read_only=True)
    license_sub_category = serializers.CharField(source='license_sub_category.description', read_only=True)
    establishment_name = serializers.SerializerMethodField()
    site_district = serializers.CharField(source='excise_district.district', read_only=True)
    salesman_barman_role = serializers.SerializerMethodField()
    yearly_license_fee = serializers.SerializerMethodField()

    def get_is_approved(self, obj):
        src = getattr(obj, "source_application", None)
        if src is None:
            return True
        is_app = getattr(src, "is_approved", False)
        stage_name = ""
        if hasattr(src, "current_stage") and src.current_stage:
            stage_name = str(src.current_stage.name).strip().lower()
        return bool(is_app or stage_name == "approved")

    def get_is_license_fee_paid(self, obj):
        src = getattr(obj, "source_application", None)
        if src is None:
            # For some issued licenses (especially renewals), source_application may not resolve reliably.
            # Treat such licenses as "paid" for menu gating since issuance typically implies fees were handled.
            return True
        if obj.source_type == "company_registration":
            return getattr(src, "payment_amount", None) is not None or getattr(src, "is_approved", False)
        return bool(getattr(src, "is_license_fee_paid", False))

    def get_is_security_fee_paid(self, obj):
        src = getattr(obj, "source_application", None)
        if src is None or obj.source_type == "company_registration":
            return True
        return bool(getattr(src, "is_security_fee_paid", False))

    def get_establishment_name(self, obj):
        src = getattr(obj, "source_application", None)
        if src is not None:
            if getattr(src, "company_name", None):
                return str(getattr(src, "company_name") or "")
            if getattr(src, "establishment_name", None):
                return str(getattr(src, "establishment_name") or "")
        return str(getattr(obj, "license_id", "") or "")

    def get_salesman_barman_role(self, obj):
        if obj.source_type == 'salesman_barman':
            src = getattr(obj, "source_application", None)
            if src is not None and getattr(src, "role", None):
                return str(src.role).strip()
        return None

    def get_yearly_license_fee(self, obj):
        if obj.source_type == "company_registration":
            try:
                from django.apps import apps
                FixedFee = apps.get_model('core', 'MasterFixedFee')
                fee_obj = FixedFee.objects.filter(fee_code='COMP_REG', is_active=True).first()
                return float(fee_obj.amount) if fee_obj else 5000.0
            except Exception:
                return 5000.0
        src = getattr(obj, "source_application", None)
        return float(getattr(src, "yearly_license_fee", 0) or 0)

    def _get_timer_days(self, code: str, default_days: int) -> float:
        cfg = (
            SupplyChainTimerConfig.objects.filter(code=code, is_active=True)
            .order_by("-updated_at", "-id")
            .first()
        )
        if not cfg:
            return float(default_days)

        unit = str(getattr(cfg, "delay_unit", "") or "").lower().strip()
        value = getattr(cfg, "delay_value", None)
        try:
            value_int = max(0, int(value or 0))
        except (TypeError, ValueError):
            value_int = 0

        if value_int > 0 and unit:
            if unit.endswith("s"):
                unit = unit[:-1]
            if unit == "day":
                return float(value_int)
            if unit in ("week", "wk"):
                return float(value_int * 7)
            if unit in ("month", "mon", "mo"):
                return float(value_int * 30)
            if unit in ("year", "yr"):
                return float(value_int * 365)
            if unit in ("hour", "hr"):
                return float(value_int) / 24.0
            if unit in ("minute", "min"):
                return float(value_int) / (24.0 * 60.0)
            if unit in ("second", "sec"):
                return float(value_int) / (24.0 * 3600.0)

        days = getattr(cfg, "validity_period_days", None)
        if days is not None:
            try:
                return float(max(0, int(days)))
            except (TypeError, ValueError):
                return float(default_days)

        return float(default_days)

    def _license_is_valid_now(self, obj) -> bool:
        now_dt = timezone.now()
        if not bool(getattr(obj, "is_active", True)):
            return False
        if getattr(obj, "issue_date", None) and obj.issue_date > now_dt:
            return False
        if getattr(obj, "valid_up_to", None) and obj.valid_up_to < now_dt:
            return False
        return True

    def _license_is_expired(self, obj) -> bool:
        now_dt = timezone.now()
        return bool(getattr(obj, "valid_up_to", None) and obj.valid_up_to < now_dt)

    def _renewal_window(self, obj):
        now_dt = timezone.now()
        reminder_days = self._get_timer_days("LICENSE_RENEWAL_REMINDER_TIMER", 90)
        valid_up_to = getattr(obj, "valid_up_to", None)
        if not valid_up_to:
            return reminder_days, None, None, False
        window_start = valid_up_to - timedelta(days=reminder_days)
        window_end = valid_up_to
        can_renew = now_dt >= window_start
        return reminder_days, window_start, window_end, can_renew

    def get_issue_date(self, obj):
        d = getattr(obj, "issue_date", None)
        return d.isoformat() if d else None

    def get_valid_up_to(self, obj):
        d = getattr(obj, "valid_up_to", None)
        return d.isoformat() if d else None

    def get_issue_date_display(self, obj):
        d = getattr(obj, "issue_date", None)
        return d.strftime("%d/%m/%Y") if d else ""

    def get_valid_up_to_display(self, obj):
        d = getattr(obj, "valid_up_to", None)
        return d.strftime("%d/%m/%Y") if d else ""

    def get_is_expired(self, obj):
        return self._license_is_expired(obj)

    def get_is_valid_now(self, obj):
        return self._license_is_valid_now(obj)

    def get_can_access_supply_chain(self, obj):
        paid = bool(self.get_is_license_fee_paid(obj) and self.get_is_security_fee_paid(obj))
        return bool(paid and self._license_is_valid_now(obj))

    def get_can_renew(self, obj):
        _reminder_days, _start, _end, can_renew = self._renewal_window(obj)
        return bool(can_renew)

    def get_renewal_window_starts_on(self, obj):
        _reminder_days, start, _end, _can = self._renewal_window(obj)
        return start.isoformat() if start else None

    def get_renewal_window_ends_on(self, obj):
        _reminder_days, _start, end, _can = self._renewal_window(obj)
        return end.isoformat() if end else None

    def get_reminder_window_days(self, obj):
        reminder_days, _start, _end, _can = self._renewal_window(obj)
        return int(reminder_days)

    def get_renewal_count(self, obj):
        try:
            from models.transactional.license_renewal_application.models import LicenseApplication
            return LicenseApplication.objects.filter(old_license_id=obj.license_id, is_approved=True).count()
        except Exception:
            return 0

    def get_renewal_details(self, obj):
        try:
            from models.transactional.license_renewal_application.models import LicenseApplication
            qs = LicenseApplication.objects.filter(old_license_id=obj.license_id, is_approved=True).order_by('updated_at')
            details = []
            for app in qs:
                dt = app.updated_at or app.created_at
                date_str = dt.strftime("%d/%m/%Y") if dt else ""
                details.append({
                    "application_id": app.application_id,
                    "date": date_str
                })
            return details
        except Exception:
            return []

    class Meta:
        model = License
        fields = [
            'license_id',
            'source_object_id',
            'is_active',
            'is_approved',
            'is_license_fee_paid',
            'is_security_fee_paid',
            'issue_date',
            'valid_up_to',
            'issue_date_display',
            'valid_up_to_display',
            'is_expired',
            'is_valid_now',
            'can_access_supply_chain',
            'can_renew',
            'renewal_window_starts_on',
            'renewal_window_ends_on',
            'reminder_window_days',
            'first_name',
            'middle_name',
            'last_name',
            'username',
            'email',
            'phone_number',
            'role',
            'district',
            'application_type',
            'license_category',
            'license_sub_category_id',
            'license_sub_category',
            'establishment_name',
            'site_district',
            'renewal_count',
            'renewal_details',
            'salesman_barman_role',
            'yearly_license_fee',
        ]
