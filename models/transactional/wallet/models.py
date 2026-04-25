from django.db import models
from django.utils import timezone


def _looks_like_distillery(text: str) -> bool:
    t = str(text or "").strip().lower()
    return "distill" in t


def _looks_like_brewery(text: str) -> bool:
    t = str(text or "").strip().lower()
    return ("brew" in t) or ("beer" in t)


def _resolve_approved_license_id(raw_value: str) -> str:
    """
    Normalize any incoming licensee/profile id to the approved license_id format (typically NA/...).
    """
    value = str(raw_value or "").strip()
    if not value:
        return ""

    try:
        from models.masters.license.models import License
    except Exception:
        return value

    active_qs = License.objects.filter(is_active=True)

    hit = active_qs.filter(license_id=value).order_by("-issue_date", "-license_id").first()
    if hit and hit.license_id:
        return str(hit.license_id).strip()

    hit = active_qs.filter(source_object_id=value).order_by("-issue_date", "-license_id").first()
    if hit and hit.license_id:
        return str(hit.license_id).strip()

    if value.startswith("NLI/"):
        alias = f"NA/{value[4:]}"
        hit = active_qs.filter(license_id=alias).order_by("-issue_date", "-license_id").first()
        if hit and hit.license_id:
            return str(hit.license_id).strip()
    elif value.startswith("NA/"):
        alias = f"NLI/{value[3:]}"
        hit = active_qs.filter(source_object_id=alias).order_by("-issue_date", "-license_id").first()
        if hit and hit.license_id:
            return str(hit.license_id).strip()

    try:
        from auth.user.models import CustomUser
    except Exception:
        CustomUser = None

    if CustomUser:
        user = CustomUser.objects.filter(username__iexact=value).first()
        if user:
            hit = (
                active_qs.filter(applicant=user, license_id__istartswith="NA/")
                .order_by("-issue_date", "-license_id")
                .first()
            )
            if hit and hit.license_id:
                return str(hit.license_id).strip()
            hit = (
                active_qs.filter(applicant=user, source_type="new_license_application")
                .order_by("-issue_date", "-license_id")
                .first()
            )
            if hit and hit.license_id:
                return str(hit.license_id).strip()

    try:
        from models.masters.supply_chain.profile.models import SupplyChainUserProfile, UserManufacturingUnit
    except Exception:
        SupplyChainUserProfile = None
        UserManufacturingUnit = None

    if SupplyChainUserProfile:
        prof = SupplyChainUserProfile.objects.filter(licensee_id=value).select_related("user").first()
        if prof and getattr(prof, "user_id", None):
            hit = (
                active_qs.filter(applicant_id=prof.user_id, license_id__istartswith="NA/")
                .order_by("-issue_date", "-license_id")
                .first()
            )
            if hit and hit.license_id:
                return str(hit.license_id).strip()
            hit = (
                active_qs.filter(applicant_id=prof.user_id, source_type="new_license_application")
                .order_by("-issue_date", "-license_id")
                .first()
            )
            if hit and hit.license_id:
                return str(hit.license_id).strip()

    if UserManufacturingUnit:
        unit = UserManufacturingUnit.objects.filter(licensee_id=value).select_related("user").first()
        if unit and getattr(unit, "user_id", None):
            hit = (
                active_qs.filter(applicant_id=unit.user_id, license_id__istartswith="NA/")
                .order_by("-issue_date", "-license_id")
                .first()
            )
            if hit and hit.license_id:
                return str(hit.license_id).strip()
            hit = (
                active_qs.filter(applicant_id=unit.user_id, source_type="new_license_application")
                .order_by("-issue_date", "-license_id")
                .first()
            )
            if hit and hit.license_id:
                return str(hit.license_id).strip()

    if CustomUser and "/" not in value:
        hit = (
            License.objects.filter(
                applicant__username__iexact=value,
                is_active=True,
                license_id__istartswith="NA/",
            )
            .order_by("-issue_date", "-license_id")
            .first()
        )
        if hit and hit.license_id:
            return str(hit.license_id).strip()
        hit = (
            License.objects.filter(
                source_type="new_license_application",
                applicant__username__iexact=value,
            )
            .order_by("-is_active", "-issue_date", "-license_id")
            .first()
        )
        if hit and hit.license_id:
            return str(hit.license_id).strip()

    if CustomUser and value.isdigit():
        hit = (
            active_qs.filter(applicant_id=int(value), license_id__istartswith="NA/")
            .order_by("-issue_date", "-license_id")
            .first()
        )
        if hit and hit.license_id:
            return str(hit.license_id).strip()
        hit = (
            active_qs.filter(applicant_id=int(value), source_type="new_license_application")
            .order_by("-issue_date", "-license_id")
            .first()
        )
        if hit and hit.license_id:
            return str(hit.license_id).strip()

    if CustomUser and "/" not in value:
        user = CustomUser.objects.filter(username__iexact=value).first()
        if user:
            hit = License.objects.filter(applicant=user, license_id__istartswith="NA/").order_by(
                "-issue_date", "-license_id"
            ).first()
            if hit and hit.license_id:
                return str(hit.license_id).strip()
            hit = License.objects.filter(applicant=user, source_type="new_license_application").order_by(
                "-issue_date", "-license_id"
            ).first()
            if hit and hit.license_id:
                return str(hit.license_id).strip()

    return value


def _resolve_wallet_row_licensee_id(licensee_id: str, user_id: str = "") -> str:
    raw_lic = str(licensee_id or "").strip()
    raw_uid = str(user_id or "").strip()
    for candidate in (raw_lic, raw_uid):
        if not candidate:
            continue
        resolved = _resolve_approved_license_id(candidate)
        if resolved and "/" in resolved:
            return resolved
    return _resolve_approved_license_id(raw_lic) or raw_lic


def _resolve_module_type_from_license_id(license_id_value: str, fallback: str = "") -> str:
    value = str(license_id_value or "").strip()
    if not value:
        return str(fallback or "").strip()

    try:
        from models.masters.license.models import License
    except Exception:
        return str(fallback or "").strip()

    active_qs = License.objects.filter(is_active=True)
    lic = active_qs.filter(license_id=value).order_by("-issue_date", "-license_id").first()
    if not lic:
        lic = active_qs.filter(source_object_id=value).order_by("-issue_date", "-license_id").first()

    if not lic and value.startswith("NLI/"):
        alias = f"NA/{value[4:]}"
        lic = active_qs.filter(license_id=alias).order_by("-issue_date", "-license_id").first()
    elif not lic and value.startswith("NA/"):
        alias = f"NLI/{value[3:]}"
        lic = active_qs.filter(source_object_id=alias).order_by("-issue_date", "-license_id").first()

    if not lic:
        return str(fallback or "").strip()

    sub_category = getattr(lic, "license_sub_category", None)
    sub_desc = str(getattr(sub_category, "description", "") or "").strip().lower()
    if _looks_like_distillery(sub_desc):
        return "distillery"
    if _looks_like_brewery(sub_desc):
        return "brewery"

    # Do NOT map by numeric subcategory IDs; IDs vary between environments and can cause
    # non-manufacturing licenses (e.g. Departmental Store) to be misclassified.

    source = getattr(lic, "source_application", None)
    license_type = getattr(source, "license_type", None) if source is not None else None
    type_name = str(getattr(license_type, "license_type", "") or "").strip().lower()
    if _looks_like_distillery(type_name):
        return "distillery"
    if _looks_like_brewery(type_name):
        return "brewery"

    return str(fallback or "").strip()

class WalletBalance(models.Model):
    wallet_balance_id = models.BigAutoField(primary_key=True)
    licensee_id = models.CharField(max_length=50)
    licensee_name = models.CharField(max_length=150, null=True, blank=True)
    manufacturing_unit = models.CharField(max_length=150, null=True, blank=True)
    user_id = models.CharField(max_length=50, null=True, blank=True)
    module_type = models.CharField(max_length=20)
    wallet_type = models.CharField(max_length=30)
    head_of_account = models.CharField(max_length=50)
    opening_balance = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_credit = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_debit = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    current_balance = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    last_updated_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "wallet_balances"

    def save(self, *args, **kwargs):
        merged = _resolve_wallet_row_licensee_id(self.licensee_id, getattr(self, "user_id", "") or "")
        if merged:
            self.licensee_id = merged
        self.module_type = _resolve_module_type_from_license_id(self.licensee_id, fallback=self.module_type or "other")
        uf = kwargs.get("update_fields")
        if uf is not None:
            uf = list(uf)
            for name in ("licensee_id", "module_type"):
                if name not in uf:
                    uf.append(name)
            kwargs["update_fields"] = uf
        super().save(*args, **kwargs)


class WalletTransaction(models.Model):
    wallet_transaction_id = models.BigAutoField(primary_key=True)
    wallet_balance = models.ForeignKey(
        WalletBalance,
        on_delete=models.RESTRICT,
        db_column="wallet_balance_id",
    )
    transaction_id = models.CharField(max_length=100)
    licensee_id = models.CharField(max_length=50)
    licensee_name = models.CharField(max_length=150, null=True, blank=True)
    user_id = models.CharField(max_length=50, null=True, blank=True)
    module_type = models.CharField(max_length=20)
    wallet_type = models.CharField(max_length=30)
    head_of_account = models.CharField(max_length=50)
    entry_type = models.CharField(max_length=10)
    transaction_type = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    balance_before = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    balance_after = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    reference_no = models.CharField(max_length=100, null=True, blank=True)
    source_module = models.CharField(max_length=50)
    payment_status = models.CharField(max_length=20)
    remarks = models.CharField(max_length=300, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "wallet_transactions"

    def save(self, *args, **kwargs):
        self.licensee_id = _resolve_wallet_row_licensee_id(self.licensee_id, getattr(self, "user_id", "") or "")
        self.module_type = _resolve_module_type_from_license_id(self.licensee_id, fallback=self.module_type)
        uf = kwargs.get("update_fields")
        if uf is not None:
            uf = list(uf)
            for name in ("licensee_id", "module_type"):
                if name not in uf:
                    uf.append(name)
            kwargs["update_fields"] = uf
        super().save(*args, **kwargs)

