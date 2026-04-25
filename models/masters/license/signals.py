from datetime import date
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from auth.workflow.models import Transaction
from .models import License
import logging

logger = logging.getLogger(__name__)


def _stage_is_commissioner_approval(stage, *, application_model: str) -> bool:
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
    app = (application_model or "").lower()
    if app != "newlicenseapplication":
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
    name_lower = str(getattr(stage, "name", "") or "").strip().lower()
    if not name_lower or "reject" in name_lower:
        return False
    if (application_model or "").lower() != "newlicenseapplication":
        return False
    if name_lower == "awaiting_payment":
        return True
    if "awaiting" in name_lower and "payment" in name_lower:
        return True
    return False


def _stage_should_issue_license(stage, *, application_model: str) -> bool:
    """
    Decide when a new Transaction should create a License (NA/... / LA/... / SB/...) and wallet rows.

    New license applications: issue license_id (NA/...) and seed wallet_balances (0 balance) when
    the workflow reaches commissioner approval and/or "Awaiting License Fee Payment" (`awaiting_payment`).

    Other application types keep the legacy rule: exact stage name "approved".
    """
    if not stage:
        return False
    name_lower = str(getattr(stage, "name", "") or "").strip().lower()
    if not name_lower:
        return False
    if "reject" in name_lower:
        return False

    app = (application_model or "").lower()
    if app == "newlicenseapplication":
        # Different deployments use slightly different stage naming:
        # - "Commissioner" (or "Commissioner Approval")
        # - "awaiting_payment" ("Awaiting License Fee Payment")
        # - final "approved" stage
        # To keep behavior stable, issue the NA/... license (and seed wallets) on any of these.
        return bool(
            _stage_is_commissioner_approval(stage, application_model=application_model)
            or _stage_is_awaiting_license_fee_payment(stage, application_model=application_model)
            or (getattr(stage, "is_final", False) and "reject" not in name_lower)
            or name_lower == "approved"
        )

    return name_lower == "approved"


def get_license_valid_up_to(issue_date: date) -> date:
    year = issue_date.year
    if issue_date.month >= 3:  
        end_year = year + 1
    else: 
        end_year = year
    return date(end_year, 3, 31)


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
    if not _stage_should_issue_license(instance.stage, application_model=application_model):
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
        if application_model == "newlicenseapplication" and (
            _stage_is_commissioner_approval(instance.stage, application_model=application_model)
            or _stage_is_awaiting_license_fee_payment(instance.stage, application_model=application_model)
        ):
            try:
                from models.transactional.wallet.wallet_initializer import (
                    initialize_wallet_balances_for_license,
                )

                initialize_wallet_balances_for_license(existing_license)
            except Exception as wallet_error:
                logger.error(
                    "Wallet initialization failed for existing license_id=%s (commissioner/awaiting_payment): %s",
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
        
        if not license_category or not excise_district:
            logger.warning(f"Application {application.pk} missing license_category or district")
            return
    except AttributeError as e:
        logger.error(f"Error accessing fields on {type(application)}: {e}")
        return
    
    issue_date = instance.timestamp.date()
    is_renewal = hasattr(application, 'renewal_of') and application.renewal_of is not None

    def get_current_fy_end(d):
        y = d.year
        if d.month >= 4:
            return date(y + 1, 3, 31)
        else:
            return date(y, 3, 31)

    if is_renewal:
        valid_up_to = get_current_fy_end(issue_date).replace(year=get_current_fy_end(issue_date).year + 1)
    else:
        valid_up_to = get_current_fy_end(issue_date)

    # === license_id logic ===
    district_code = str(excise_district.district_code)

    if is_renewal:
        # Force NEXT financial year
        renewal_year = issue_date.year
        if issue_date.month >= 4:
            fin_year = f"{renewal_year}-{str(renewal_year + 1)[2:]}"
        else:
            fin_year = f"{renewal_year}-{str(renewal_year + 1)[2:]}"  # Jan-Mar 2026 → 2026-27
    else:
        # Let model handle it (but we can still use same logic for consistency)
        if issue_date.month >= 4:
            fin_year = f"{issue_date.year}-{str(issue_date.year + 1)[2:]}"
        else:
            fin_year = f"{issue_date.year - 1}-{str(issue_date.year)[2:]}"  # 2025-26

    prefix_map = {'new_license_application': 'NA', 'license_application': 'LA', 'salesman_barman': 'SB'}
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
        created_license = License.objects.create(
            license_id=new_license_id,
            source_content_type=ct,
            source_object_id=str(application.pk),
            source_type=source_type,
            applicant=applicant,
            license_category=license_category,
            license_sub_category=license_sub_category,
            excise_district=excise_district,
            issue_date=issue_date,
            valid_up_to=valid_up_to,
            is_active=True
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

        # === NEW: If this is a renewal, deactivate the old license ===
        if hasattr(application, 'renewal_of') and application.renewal_of:
            old_license = application.renewal_of
            if old_license.is_active:
                old_license.is_active = False
                old_license.save(update_fields=['is_active'])
                logger.info(f"Deactivated previous license {old_license.license_id} due to renewal")

        # === NEW: Create/Update Supply Chain User Profile ===
        try:
            establishment_name = str(getattr(application, 'establishment_name', '') or '').strip()
            if establishment_name and applicant:
                from models.masters.supply_chain.profile.models import (
                    SupplyChainUserProfile,
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
                
                # Create/Update active profile (only if user doesn't have one yet)
                if not SupplyChainUserProfile.objects.filter(user=applicant).exists():
                    SupplyChainUserProfile.objects.create(
                        user=applicant,
                        manufacturing_unit_name=establishment_name,
                        licensee_id=created_license.license_id,
                        license_type=license_type,
                        address=getattr(application, 'site_address', '') or ''
                    )
                    logger.info(f"Created supply chain profile for user {applicant.id} with license {created_license.license_id}")
                else:
                    logger.info(f"User {applicant.id} already has supply chain profile, skipping creation")
                    
        except Exception as profile_error:
            logger.error(
                "License created but supply chain profile creation failed for license_id=%s: %s",
                created_license.license_id,
                profile_error,
            )

    except Exception as e:
        logger.error(f"Failed to create license for {application.pk}: {e}")
