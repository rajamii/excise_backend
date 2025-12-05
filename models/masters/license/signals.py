# licenses/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from auth.workflow.models import Transaction
from .models import License


@receiver(post_save, sender=Transaction)
def create_license_on_final_approval(sender, instance, created, **kwargs):
    if not created:
        return

    # Only trigger when transitioning TO "approved" stage
    if instance.stage.name != "approved":
        return

    application = instance.application
    if not application:
        return

    # Prevent duplicate license creation
    ct = ContentType.objects.get_for_model(application)
    if License.objects.filter(
        source_content_type=ct,
        source_object_id=str(application.pk)
    ).exists():
        return

    # Map model → source_type
    model_name = application._meta.model_name.lower()
    source_type_map = {
        'new_license_application': 'New License Application',
        'license_application': 'License Application',
        'salesman_barman': 'Salesman/Barman',
    }

    source_type = source_type_map.get(model_name)
    if not source_type:
        return  # Unknown model — skip safely

    # All three models have license_category
    try:
        license_category = application.license_category
        excise_district = application.excise_district
    except AttributeError:
        return  # Safety

    License.objects.create(
        source_content_type=ct,
        source_object_id=str(application.pk),
        source_application=application,
        source_type=source_type,
        license_category=license_category,
        excise_district=excise_district,
        issue_date=timezone.now().date(),
        valid_up_to=timezone.now().date().replace(year=timezone.now().year + 1),
        is_active=True
    )