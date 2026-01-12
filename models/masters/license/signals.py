from datetime import date
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from auth.workflow.models import Transaction
from .models import License
import logging

logger = logging.getLogger(__name__)

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

    if instance.stage.name != "approved":
        return

    # CRITICAL: Manually resolve the generic relation
    if instance.content_type is None or instance.object_id is None:
        logger.warning(f"Transaction {instance.id} has no content_type or object_id")
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

    # Prevent duplicate license
    ct = instance.content_type

    if License.objects.filter(
        source_content_type=ct,
        source_object_id=instance.object_id
    ).exists():
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
        excise_district = getattr(application, 'excise_district', None) or getattr(application, 'site_district', None)
        
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
        License.objects.create(
            license_id=new_license_id,
            source_content_type=ct,
            source_object_id=str(application.pk),
            source_type=source_type,
            license_category=license_category,
            excise_district=excise_district,
            issue_date=issue_date,
            valid_up_to=valid_up_to,
            is_active=True
        )
        logger.info(f"License created for application {application.pk}")

        # === NEW: If this is a renewal, deactivate the old license ===
        if hasattr(application, 'renewal_of') and application.renewal_of:
            old_license = application.renewal_of
            if old_license.is_active:
                old_license.is_active = False
                old_license.save(update_fields=['is_active'])
                logger.info(f"Deactivated previous license {old_license.license_id} due to renewal")

    except Exception as e:
        logger.error(f"Failed to create license for {application.pk}: {e}")