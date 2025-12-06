from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from auth.workflow.models import Transaction
from .models import License
import logging

logger = logging.getLogger(__name__)

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

    try:
        License.objects.create(
            source_content_type=ct,
            source_object_id=str(application.pk),
            source_type=source_type,
            license_category=license_category,
            excise_district=excise_district,
            issue_date=instance.timestamp.date(),
            valid_up_to=instance.timestamp.date().replace(year=instance.timestamp.year + 1),
            is_active=True
        )
        logger.info(f"License created for application {application.pk}")
    except Exception as e:
        logger.error(f"Failed to create license for {application.pk}: {e}")