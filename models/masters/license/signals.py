from datetime import date, datetime, time
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from auth.workflow.models import Transaction
from .models import License
import logging

logger = logging.getLogger(__name__)


def _stage_is_commissioner_approval(stage) -> bool:
    """
    New license applications: license + wallet_balances (0 balance) are issued only when
    the workflow stage is a commissioner approval (not OIC / other intermediate approvals).
    Stage name may be stored as just `Commissioner` in the DB; treat that as approval for
    new-license issuance and wallet initialization.
    """
    if not stage:
        return False
    name_lower = str(getattr(stage, "name", "") or "").strip().lower()
    if not name_lower or "reject" in name_lower:
        return False
    # Exclude Joint Commissioner stage (it is an intermediate review stage in workflow_id=1).
    if "joint" in name_lower:
        return False

    # Some datasets store commissioner stage as exactly "Commissioner"/"Commisioner" without "approve".
    if name_lower in {"commissioner", "commisioner"}:
        return True

    # More explicit naming variants (Commissioner Approval / Approved by Commissioner / etc.)
    if ("commissioner" in name_lower or "commisioner" in name_lower) and (
        "approv" in name_lower or "approved" in name_lower
    ):
        return True

    return False


def _stage_is_awaiting_license_fee_payment(stage, *, application_model: str) -> bool:
    """
    New license applications: e.g. workflow stage id 23 — name `awaiting_payment`,
    label "Awaiting License Fee Payment". Issuing the NA/... license here ensures wallets
    exist before the licensee pays the license fee (correct licensee_id on first insert).
    """
    if not stage:
        return False
    raw_name = str(getattr(stage, "name", "") or "").strip()
    name_lower = raw_name.lower()
    if not name_lower or "reject" in name_lower:
        return False
    if (application_model or "").lower() != "newlicenseapplication":
        return False

    # IMPORTANT:
    # "Awaiting Payment" can exist in multiple workflows (e.g. application fee payment gate).
    # We should only treat the specific stage that represents "Awaiting License Fee Payment"
    # as the trigger to issue the NA/... license and seed wallets.
    normalized = name_lower.replace("-", "_").replace(" ", "_")
    desc_lower = str(getattr(stage, "description", "") or "").strip().lower()

    # Prefer an explicit stage id match when deployments use the canonical id=23.
    try:
        if int(getattr(stage, "id", 0) or 0) == 23:
            return True
    except Exception:
        pass

    if normalized == "awaiting_payment":
        # Disambiguate by description text where available.
        if "license" in desc_lower and "fee" in desc_lower:
            return True
        if "license_fee" in desc_lower or "licensefee" in desc_lower:
            return True

    return False


def _stage_should_issue_license(instance, *, application_model: str) -> bool:
    """
    Decide when a new Transaction should create a License (NA/... / LA/... / SB/...) and wallet rows.

    For new licensee and salesman barman applications, the license row is created
    only when the Commissioner approves the application (transitioning out of the Commissioner stage).

    Other application types keep the legacy rule: exact stage name "approved".
    """
    from auth.workflow.models import WorkflowStage
    if isinstance(instance, WorkflowStage):
        stage = instance
        txn = None
    else:
        stage = getattr(instance, "stage", None)
        txn = instance

    if not stage:
        return False
    name_lower = str(getattr(stage, "name", "") or "").strip().lower()
    if not name_lower or "reject" in name_lower or "objection" in name_lower:
        return False

    app = (application_model or "").lower()
    if app in {"newlicenseapplication", "salesmanbarmanmodel", "companyregistration"}:
        if txn is None:
            return bool(
                _stage_is_commissioner_approval(stage)
                or (getattr(stage, "is_final", False) and "reject" not in name_lower)
                or name_lower == "approved"
            )
        
        # Exclude stages that represent resubmission/backward steps or objections
        invalid_targets = {"applied", "district", "enquiry", "joint", "commissioner", "commisioner", "objection", "reject"}
        if any(t in name_lower for t in invalid_targets):
            return False

        if not txn.content_type_id or not txn.object_id:
            return False
        previous_txn = Transaction.objects.filter(
            content_type_id=txn.content_type_id,
            object_id=txn.object_id,
            id__lt=txn.id
        ).order_by('-id').first()
        if not previous_txn:
            return False
        prev_stage_name = str(getattr(previous_txn.stage, "name", "") or "").strip().lower()
        if "joint" in prev_stage_name:
            return False
        return prev_stage_name in {"commissioner", "commisioner"}

    # Other application types: deployments often use commissioner final stage naming instead of "approved".
    return bool(
        _stage_is_commissioner_approval(stage)
        or (getattr(stage, "is_final", False) and "reject" not in name_lower)
        or name_lower == "approved"
    )



def _new_license_payments_complete(application) -> bool:
    return bool(
        getattr(application, "is_license_fee_paid", False)
        and getattr(application, "is_security_fee_paid", False)
    )


def _get_dynamic_renewal_date():
    from models.masters.core.models import RenewalApplicationConfig
    config = RenewalApplicationConfig.objects.first()
    if config:
        return config.renewal_month, config.renewal_day, config.renewal_time
    return 3, 31, time.max.replace(microsecond=0)


def get_license_valid_up_to(issue_date: date) -> datetime:
    """
    Returns the FY end as an aware datetime (end-of-day) from RenewalApplicationConfig.

    Accepts either a `date` or `datetime` input.
    """
    from zoneinfo import ZoneInfo
    from models.masters.core.models import RenewalApplicationConfig
    
    issue_day = issue_date.date() if isinstance(issue_date, datetime) else issue_date
    year = issue_day.year
    
    config = RenewalApplicationConfig.objects.first()
    r_month = config.renewal_month if config else 3
    r_day = config.renewal_day if config else 31
    r_time = config.renewal_time if config else time(23, 59, 59)
    
    if issue_day.month > r_month or (issue_day.month == r_month and issue_day.day >= r_day):
        end_year = year + 1
    else:
        end_year = year

    fy_end_day = date(end_year, r_month, r_day)
    fy_end_dt = datetime.combine(fy_end_day, r_time)
    tz = ZoneInfo("Asia/Kolkata")
    return timezone.make_aware(fy_end_dt, tz) if timezone.is_naive(fy_end_dt) else fy_end_dt


@receiver(post_save, sender=Transaction)
def create_license_on_final_approval(sender, instance, created, **kwargs):
    if not created:
        return

    # Safety: ensure stage is loaded
    if not hasattr(instance, 'stage') or not instance.stage:
        return

    # CRITICAL: Manually resolve the generic relation
    if instance.content_type is None or instance.object_id is None:
        logger.warning(f"Transaction {instance.id} has no content_type or object_id")
        return

    application_model = str(getattr(instance.content_type, "model", "") or "").lower()
    if not _stage_should_issue_license(instance, application_model=application_model):
        return

    try:
        # This forces the generic object to be fetched
        application = instance.content_type.get_object_for_this_type(pk=instance.object_id)
    except (ContentType.DoesNotExist, instance.content_type.model_class().DoesNotExist):
        logger.error(f"Could not resolve application for Transaction {instance.id}")
        return
    except Exception as e:
        logger.error(f"Unexpected error resolving application: {e}")
        return

    # Prevent duplicate license creation; still seed wallets on commissioner / awaiting_payment if missing.
    ct = instance.content_type

    existing_license = (
        License.objects.filter(
            source_content_type=ct,
            source_object_id=instance.object_id,
        )
        .order_by("-issue_date", "-license_id")
        .first()
    )
    if existing_license:
        if source_type := getattr(existing_license, "source_type", None):
            if source_type == "new_license_application":
                should_be_active = _new_license_payments_complete(application)
                if existing_license.is_active != should_be_active:
                    existing_license.is_active = should_be_active
                    existing_license.save(update_fields=["is_active"])
            elif source_type == "salesman_barman":
                app_print_paid = getattr(application, "is_print_fee_paid", False)
                if existing_license.is_print_fee_paid != app_print_paid:
                    existing_license.is_print_fee_paid = app_print_paid
                    existing_license.save(update_fields=["is_print_fee_paid"])
            elif source_type == "company_registration":
                should_be_active = getattr(application, "is_approved", False) and getattr(application, "payment_amount", None) is not None
                if existing_license.is_active != should_be_active:
                    existing_license.is_active = should_be_active
                    existing_license.save(update_fields=["is_active"])

        # Still ensure wallets exist (and get updated metadata) whenever an approval-stage
        # transaction is logged for the application.
        try:
            from models.transactional.wallet.wallet_initializer import (
                initialize_wallet_balances_for_license,
            )

            initialize_wallet_balances_for_license(existing_license)
        except Exception as wallet_error:
            logger.error(
                "Wallet initialization failed for existing license_id=%s (approval stage): %s",
                existing_license.license_id,
                wallet_error,
            )
        return

    # Map model name → source_type
    model_name = ct.model
    source_type_map = {
        'newlicenseapplication': 'new_license_application',
        'licenseapplication': 'license_application',
        'salesmanbarmanmodel': 'salesman_barman',
        'companyregistration': 'company_registration',
    }

    source_type = source_type_map.get(model_name)
    if not source_type:
        logger.warning(f"Unknown model for license creation: {model_name}")
        return

    # Extract required fields — with fallbacks
    try:
        license_category = getattr(application, 'license_category', None)
        license_sub_category = getattr(application, 'license_sub_category', None)
        excise_district = getattr(application, 'excise_district', None) or getattr(application, 'site_district', None)
        applicant = getattr(application, 'applicant', None)
        
        # Dynamically resolve category and district for company registrations
        from models.masters.core.models import LicenseCategory, District
        if model_name == 'companyregistration':
            if not license_category:
                lic_name = getattr(application, 'license', '')
                if lic_name:
                    license_category = LicenseCategory.objects.filter(license_category__iexact=lic_name).first()
                if not license_category:
                    license_category = LicenseCategory.objects.filter(id=1).first() or LicenseCategory.objects.first()
            if not excise_district:
                state_val = getattr(application, 'state', '')
                if state_val:
                    excise_district = District.objects.filter(district__iexact=state_val).first()
                if not excise_district:
                    excise_district = District.objects.filter(district_code=1101).first() or District.objects.first()

        if not license_category or not excise_district:
            logger.warning(f"Application {application.pk} missing license_category or district")
            return
    except AttributeError as e:
        logger.error(f"Error accessing fields on {type(application)}: {e}")
        return
    
    issue_dt = instance.timestamp if getattr(instance, "timestamp", None) else timezone.now()
    issue_day = issue_dt.date()
    is_renewal = hasattr(application, 'renewal_of') and application.renewal_of is not None

    def get_current_fy_end(d):
        y = d.year
        from models.masters.core.models import RenewalApplicationConfig
        config = RenewalApplicationConfig.objects.first()
        r_month = config.renewal_month if config else 3
        r_day = config.renewal_day if config else 31
        r_time = config.renewal_time if config else time(23, 59, 59)
        
        if d.month > r_month or (d.month == r_month and d.day >= r_day):
            return date(y + 1, r_month, r_day), r_time
        else:
            return date(y, r_month, r_day), r_time

    from models.masters.core.models import RenewalApplicationConfig
    config = RenewalApplicationConfig.objects.first()
    r_month = config.renewal_month if config else 3
    r_day = config.renewal_day if config else 31
    r_time = config.renewal_time if config else time(23, 59, 59)

    if is_renewal:
        old_lic_valid = application.renewal_of.valid_up_to
        if old_lic_valid:
            from zoneinfo import ZoneInfo
            local_old_val = timezone.localtime(old_lic_valid, ZoneInfo("Asia/Kolkata"))
            valid_day = date(local_old_val.year + 1, r_month, r_day)
            valid_time = r_time
        else:
            fy_end, valid_time = get_current_fy_end(issue_day)
            valid_day = fy_end.replace(year=fy_end.year + 1)
    else:
        valid_day, valid_time = get_current_fy_end(issue_day)

    from zoneinfo import ZoneInfo
    valid_up_to_dt = timezone.make_aware(
        datetime.combine(valid_day, valid_time),
        ZoneInfo("Asia/Kolkata"),
    )

    # === license_id logic ===
    district_code = str(excise_district.district_code)

    if is_renewal:
        # Force NEXT financial year
        renewal_year = issue_day.year
        if issue_day.month >= 4:
            fin_year = f"{renewal_year}-{str(renewal_year + 1)[2:]}"
        else:
            fin_year = f"{renewal_year}-{str(renewal_year + 1)[2:]}"  # Jan-Mar 2026 → 2026-27
    else:
        # Let model handle it (but we can still use same logic for consistency)
        if issue_day.month >= 4:
            fin_year = f"{issue_day.year}-{str(issue_day.year + 1)[2:]}"
        else:
            fin_year = f"{issue_day.year - 1}-{str(issue_day.year)[2:]}"  # 2025-26

    prefix_map = {
        'new_license_application': 'NA',
        'license_application': 'LA',
        'salesman_barman': 'SB',
        'company_registration': 'CR'
    }
    prefix = prefix_map.get(source_type, 'XX')
    base_prefix = f"{prefix}/{district_code}/{fin_year}"

    # Get next sequence
    last_license = License.objects.filter(license_id__startswith=base_prefix + "/").order_by('-license_id').first()
    seq = 1
    if last_license:
        try:
            seq = int(last_license.license_id.split('/')[-1]) + 1
        except:
            pass
    new_license_id = f"{base_prefix}/{str(seq).zfill(4)}"

    try:
        license_is_active = (
            source_type not in ["new_license_application", "company_registration"]
            or (source_type == "new_license_application" and _new_license_payments_complete(application))
            or (source_type == "company_registration" and getattr(application, "is_approved", False) and getattr(application, "payment_amount", None) is not None)
        )

        created_license = License.objects.create(
            license_id=new_license_id,
            source_content_type=ct,
            source_object_id=str(application.pk),
            source_type=source_type,
            applicant=applicant,
            license_category=license_category,
            license_sub_category=license_sub_category,
            excise_district=excise_district,
            issue_date=issue_dt,
            valid_up_to=valid_up_to_dt,
            is_active=license_is_active,
            is_print_fee_paid=getattr(application, "is_print_fee_paid", False)
        )
        logger.info(f"License created for application {application.pk}")

        # Initialize module wallets for newly issued license.
        try:
            from models.transactional.wallet.wallet_initializer import (
                initialize_wallet_balances_for_license,
            )

            initialize_wallet_balances_for_license(created_license)
        except Exception as wallet_error:
            logger.error(
                "License created but wallet initialization failed for license_id=%s: %s",
                created_license.license_id,
                wallet_error,
            )

        if created_license.is_active and source_type == "new_license_application":
            try:
                from models.transactional.new_license_application.payment_status import (
                    sync_master_factory_for_license,
                )

                sync_master_factory_for_license(created_license)
            except Exception as factory_error:
                logger.error(
                    "License created but master factory sync failed for license_id=%s: %s",
                    created_license.license_id,
                    factory_error,
                )

        # === NEW: If this is a renewal, deactivate the old license ===
        if hasattr(application, 'renewal_of') and application.renewal_of:
            old_license = application.renewal_of
            if old_license.is_active:
                old_license.is_active = False
                old_license.save(update_fields=['is_active'])
                logger.info(f"Deactivated previous license {old_license.license_id} due to renewal")

        # === Supply-chain manufacturing unit mapping (no active profile table) ===
        try:
            establishment_name = str(getattr(application, 'establishment_name', '') or '').strip()
            if source_type == "new_license_application" and not created_license.is_active:
                establishment_name = ""
            if establishment_name and applicant:
                from models.masters.supply_chain.profile.models import (
                    UserManufacturingUnit
                )
                
                # Determine license type
                license_type = 'Distillery'  # Default
                if license_category:
                    category_name = str(
                        getattr(license_category, "license_category", None)
                        or getattr(license_category, "category_name", None)
                        or ""
                    ).lower()
                    if 'beer' in category_name or 'brewery' in category_name:
                        license_type = 'Brewery'
                
                # Create/Update in permanent history
                UserManufacturingUnit.objects.update_or_create(
                    user=applicant,
                    licensee_id=created_license.license_id,
                    defaults={
                        'manufacturing_unit_name': establishment_name,
                        'license_type': license_type,
                        'address': getattr(application, 'site_address', '') or ''
                    }
                )
                    
        except Exception as profile_error:
            logger.error(
                "License created but supply-chain manufacturing unit mapping failed for license_id=%s: %s",
                created_license.license_id,
                profile_error,
            )

    except Exception as e:
        logger.error(f"Failed to create license for {application.pk}: {e}")
