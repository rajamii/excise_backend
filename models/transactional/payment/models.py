from django.db import models
from django.utils import timezone

def _resolve_approved_license_id(raw_value: str) -> str:
    """
    Normalize any incoming licensee/profile id to the approved license_id format
    (typically NA/...).
    """
    value = str(raw_value or "").strip()
    if not value:
        return ""

    try:
        from models.masters.license.models import License
    except Exception:
        return value

    active_qs = License.objects.filter(is_active=True)

    # Already an approved license_id.
    hit = active_qs.filter(license_id=value).order_by("-issue_date", "-license_id").first()
    if hit and hit.license_id:
        return str(hit.license_id).strip()

    # If source object id was passed (often legacy/licensee profile id), map it.
    hit = active_qs.filter(source_object_id=value).order_by("-issue_date", "-license_id").first()
    if hit and hit.license_id:
        return str(hit.license_id).strip()

    # Common alias mapping seen in supply-chain ids.
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

    # Applicant username (e.g. legacy wallet rows keyed by user id) → latest active new license.
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

    # Legacy supply-chain profile / unit stored a non-NA id (e.g. TH...) before license was issued.
    try:
        from models.masters.supply_chain.profile.models import (
            SupplyChainUserProfile,
            UserManufacturingUnit,
        )
    except Exception:
        SupplyChainUserProfile = None
        UserManufacturingUnit = None

    if SupplyChainUserProfile:
        prof = (
            SupplyChainUserProfile.objects.filter(licensee_id=value)
            .select_related("user")
            .first()
        )
        if prof and getattr(prof, "user_id", None):
            hit = (
                active_qs.filter(
                    applicant_id=prof.user_id,
                    license_id__istartswith="NA/",
                )
                .order_by("-issue_date", "-license_id")
                .first()
            )
            if hit and hit.license_id:
                return str(hit.license_id).strip()
            hit = (
                active_qs.filter(
                    applicant_id=prof.user_id, source_type="new_license_application"
                )
                .order_by("-issue_date", "-license_id")
                .first()
            )
            if hit and hit.license_id:
                return str(hit.license_id).strip()

    if UserManufacturingUnit:
        unit = (
            UserManufacturingUnit.objects.filter(licensee_id=value)
            .select_related("user")
            .first()
        )
        if unit and getattr(unit, "user_id", None):
            hit = (
                active_qs.filter(
                    applicant_id=unit.user_id,
                    license_id__istartswith="NA/",
                )
                .order_by("-issue_date", "-license_id")
                .first()
            )
            if hit and hit.license_id:
                return str(hit.license_id).strip()
            hit = (
                active_qs.filter(
                    applicant_id=unit.user_id, source_type="new_license_application"
                )
                .order_by("-issue_date", "-license_id")
                .first()
            )
            if hit and hit.license_id:
                return str(hit.license_id).strip()

    # Direct match: wallet row used applicant username (TH...) but profile was later updated to NA/...
    # so SupplyChainUserProfile no longer has licensee_id=TH. Join License.applicant.username.
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

    # Numeric primary key passed instead of username (some clients send user id).
    if CustomUser and value.isdigit():
        hit = (
            active_qs.filter(
                applicant_id=int(value),
                license_id__istartswith="NA/",
            )
            .order_by("-issue_date", "-license_id")
            .first()
        )
        if hit and hit.license_id:
            return str(hit.license_id).strip()
        hit = (
            active_qs.filter(
                applicant_id=int(value),
                source_type="new_license_application",
            )
            .order_by("-issue_date", "-license_id")
            .first()
        )
        if hit and hit.license_id:
            return str(hit.license_id).strip()

    # Last resort: include inactive licenses for the same applicant + username.
    if CustomUser and "/" not in value:
        user = CustomUser.objects.filter(username__iexact=value).first()
        if user:
            hit = (
                License.objects.filter(
                    applicant=user,
                    license_id__istartswith="NA/",
                )
                .order_by("-issue_date", "-license_id")
                .first()
            )
            if hit and hit.license_id:
                return str(hit.license_id).strip()
            hit = (
                License.objects.filter(
                    applicant=user, source_type="new_license_application"
                )
                .order_by("-issue_date", "-license_id")
                .first()
            )
            if hit and hit.license_id:
                return str(hit.license_id).strip()

    return value


def _resolve_wallet_row_licensee_id(licensee_id: str, user_id: str = "") -> str:
    """
    Resolve licensee_id for a wallet row: try licensee_id, then user_id (often same as username).
    """
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
    if "distill" in sub_desc:
        return "distillery"
    if "brew" in sub_desc or "beer" in sub_desc:
        return "brewery"

    sub_category_id = getattr(lic, "license_sub_category_id", None)
    if sub_category_id == 1:
        return "brewery"
    if sub_category_id == 2:
        return "distillery"

    source = getattr(lic, "source_application", None)
    license_type = getattr(source, "license_type", None) if source is not None else None
    type_name = str(getattr(license_type, "license_type", "") or "").strip().lower()
    if "distill" in type_name:
        return "distillery"
    if "brew" in type_name or "beer" in type_name:
        return "brewery"

    return str(fallback or "").strip()

# Main Table for storing payment gateway parameters
class PaymentGatewayParameter(models.Model):
    sl_no = models.IntegerField(primary_key=True)
    payment_gateway_name = models.CharField(max_length=50)
    merchantid = models.CharField(max_length=100)
    securityid = models.CharField(max_length=100)
    encryption_key = models.CharField(max_length=255)
    return_url = models.CharField(max_length=500)
    created_date = models.DateTimeField(default=timezone.now)
    modified_date = models.DateTimeField(null=True, blank=True)
    is_active = models.CharField(max_length=1, default="Y")

    class Meta:
        managed = False
        db_table = "sems_payment_gateway_parameters"

    def __str__(self):
        return f"{self.sl_no} - {self.payment_gateway_name}"

# Formerly eAbgari_Payment_Trsansaction_Billdesk				
class PaymentBilldeskTransaction(models.Model):
    utr = models.CharField(max_length=100, primary_key=True)
    transaction_date = models.DateTimeField(default=timezone.now)
    transaction_id_no_hoa = models.CharField(max_length=50)
    payer_id = models.CharField(max_length=50)
    payment_module_code = models.CharField(max_length=20)
    transaction_amount = models.DecimalField(max_digits=18, decimal_places=2)

    request_merchantid = models.CharField(max_length=100, null=True, blank=True)
    request_currencytype = models.CharField(max_length=10, null=True, blank=True)
    request_typefield1 = models.CharField(max_length=10, null=True, blank=True)
    request_securityid = models.CharField(max_length=100, null=True, blank=True)
    request_typefield2 = models.CharField(max_length=10, null=True, blank=True)
    request_additionalinfo1 = models.CharField(max_length=200, null=True, blank=True)
    request_additionalinfo2 = models.CharField(max_length=200, null=True, blank=True)
    request_additionalinfo3 = models.CharField(max_length=200, null=True, blank=True)
    request_additionalinfo4 = models.CharField(max_length=200, null=True, blank=True)
    request_additionalinfo5 = models.CharField(max_length=200, null=True, blank=True)
    request_additionalinfo6 = models.CharField(max_length=200, null=True, blank=True)
    request_additionalinfo7 = models.CharField(max_length=200, null=True, blank=True)
    request_return_url = models.CharField(max_length=500, null=True, blank=True)
    request_checksum = models.CharField(max_length=500, null=True, blank=True)
    request_string = models.TextField(null=True, blank=True)

    response_string = models.TextField(null=True, blank=True)
    response_merchantid = models.CharField(max_length=100, null=True, blank=True)
    response_customerid = models.CharField(max_length=100, null=True, blank=True)
    response_txnreferenceno = models.CharField(max_length=100, null=True, blank=True)
    response_bankreferenceno = models.CharField(max_length=100, null=True, blank=True)
    response_txnamount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    response_bankid = models.CharField(max_length=50, null=True, blank=True)
    response_bankmerchantid = models.CharField(max_length=100, null=True, blank=True)
    response_txntype = models.CharField(max_length=50, null=True, blank=True)
    response_currencyname = models.CharField(max_length=10, null=True, blank=True)
    response_itemcode = models.CharField(max_length=50, null=True, blank=True)
    response_securitytype = models.CharField(max_length=50, null=True, blank=True)
    response_securityid = models.CharField(max_length=100, null=True, blank=True)
    response_securitypassword = models.CharField(max_length=100, null=True, blank=True)
    response_txndate = models.DateTimeField(null=True, blank=True)
    response_authstatus = models.CharField(max_length=10, null=True, blank=True)
    response_settlementtype = models.CharField(max_length=50, null=True, blank=True)
    response_additionalinfo1 = models.CharField(max_length=200, null=True, blank=True)
    response_additionalinfo2 = models.CharField(max_length=200, null=True, blank=True)
    response_additionalinfo3 = models.CharField(max_length=200, null=True, blank=True)
    response_additionalinfo4 = models.CharField(max_length=200, null=True, blank=True)
    response_additionalinfo5 = models.CharField(max_length=200, null=True, blank=True)
    response_additionalinfo6 = models.CharField(max_length=200, null=True, blank=True)
    response_additionalinfo7 = models.CharField(max_length=200, null=True, blank=True)
    response_errorstatus = models.CharField(max_length=50, null=True, blank=True)
    response_errordescription = models.CharField(max_length=500, null=True, blank=True)
    response_checksum = models.CharField(max_length=500, null=True, blank=True)
    response_checksum_calculated = models.CharField(max_length=500, null=True, blank=True)
    response_initial_authstatus = models.CharField(max_length=10, null=True, blank=True)
    response_initial_datetime = models.DateTimeField(null=True, blank=True)

    payment_status = models.CharField(max_length=1, default="P")
    user_id = models.CharField(max_length=50, null=True, blank=True)
    opr_date = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = "sems_payment_transaction_billdesk"

    def __str__(self):
        return f"{self.utr} ({self.payment_status})"

# Formerly eAbgari_Payment_Send_HOA
class PaymentHeadOfAccount(models.Model):
    id = models.BigAutoField(primary_key=True)
    transaction_id_no = models.CharField(max_length=50)
    head_of_account = models.CharField(max_length=50)
    # payer_id = models.CharField(max_length=50)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    payment_module_code = models.CharField(max_length=20, null=True, blank=True)
    requisition_id_no = models.CharField(max_length=50, null=True, blank=True)
    user_id = models.CharField(max_length=50, null=True, blank=True)
    opr_date = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = "sems_payment_send_hoa"


# class PaymentStatusMasterBilldesk(models.Model):
    # authstatus = models.CharField(max_length=10, primary_key=True)
    # authstatus_description = models.CharField(max_length=500)
    # payment_status = models.CharField(max_length=1)
    # created_date = models.DateTimeField(default=timezone.now)

    # class Meta:
    #     managed = False
    #     db_table = "eabgari_payment_status_master_billdesk"

    # def __str__(self):
    #     return f"{self.authstatus} -> {self.payment_status}"



class MasterHeadOfAccount(models.Model):
    head_of_account = models.CharField(max_length=50, primary_key=True)
    sl_no = models.BigIntegerField(unique=True, null=True, blank=True)
    major_head = models.CharField(max_length=10)
    sub_major_head = models.CharField(max_length=10, null=True, blank=True)
    minor_head = models.CharField(max_length=10)
    sub_head = models.CharField(max_length=10, null=True, blank=True)
    detailed_head = models.CharField(max_length=20)
    object_head = models.CharField(max_length=10, null=True, blank=True)
    detailed_head_driscription = models.CharField(max_length=500)
    pay_type = models.CharField(max_length=20, null=True, blank=True)
    visible_status = models.CharField(max_length=1, default="Y")
    created_date = models.DateTimeField(default=timezone.now)
    modified_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "sems_master_head_of_account"

    def __str__(self):
        return self.head_of_account


class MasterPaymentModule(models.Model):
    module_code = models.CharField(max_length=20, primary_key=True)
    module_desc = models.CharField(max_length=200)
    visibility_status = models.CharField(max_length=1, default="Y")
    active_payment_mode = models.CharField(max_length=1, default="O")
    payment_invoking_page = models.CharField(max_length=500, null=True, blank=True)
    payment_response_page = models.CharField(max_length=500, null=True, blank=True)
    user_id = models.CharField(max_length=50, null=True, blank=True)
    opr_date = models.DateTimeField(null=True, blank=True)
    created_date = models.DateTimeField(default=timezone.now)
    modified_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "sems_master_payment_module"

    def __str__(self):
        return f"{self.module_code} - {self.module_desc}"


class PaymentModuleHoa(models.Model):
    id = models.BigAutoField(primary_key=True)
    module_code = models.ForeignKey(
        MasterPaymentModule,
        on_delete=models.RESTRICT,
        db_column="module_code",
        to_field="module_code",
    )
    head_of_account = models.ForeignKey(
        PaymentHeadOfAccount,
        on_delete=models.RESTRICT,
        db_column="head_of_account",
        to_field="head_of_account",
    )
    # user_id = models.CharField(max_length=50, null=True, blank=True)
    opr_date = models.DateTimeField(default=timezone.now)
    is_active = models.CharField(max_length=1, default="Y")
    created_date = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = "sems_module_hoa"


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
        managed = False
        db_table = "wallet_balances"

    def save(self, *args, **kwargs):
        """
        Always persist wallet rows under the canonical issued license_id (NA/...), not legacy
        username or profile codes (TH..., etc.). Uses user_id when licensee_id alone cannot map
        (e.g. profile already updated to NA/...).
        """
        merged = _resolve_wallet_row_licensee_id(
            self.licensee_id,
            getattr(self, "user_id", "") or "",
        )
        if merged:
            self.licensee_id = merged
        self.module_type = _resolve_module_type_from_license_id(
            self.licensee_id,
            fallback=self.module_type or "other",
        )
        # Partial updates (e.g. only balances) must still persist normalized licensee_id/module_type.
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
        to_field="wallet_balance_id",
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
        managed = False
        db_table = "wallet_transactions"

    def save(self, *args, **kwargs):
        self.licensee_id = _resolve_wallet_row_licensee_id(
            self.licensee_id,
            getattr(self, "user_id", "") or "",
        )
        self.module_type = _resolve_module_type_from_license_id(
            self.licensee_id,
            fallback=self.module_type
        )
        uf = kwargs.get("update_fields")
        if uf is not None:
            uf = list(uf)
            for name in ("licensee_id", "module_type"):
                if name not in uf:
                    uf.append(name)
            kwargs["update_fields"] = uf
        super().save(*args, **kwargs)
