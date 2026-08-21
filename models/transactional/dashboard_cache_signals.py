from django.apps import apps
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from auth.workflow.models import Objection, Rejection, Transaction
from models.transactional.dashboard_cache import invalidate_dashboard_counts_cache


DASHBOARD_MODEL_LABELS = (
    ("company_registration", "CompanyRegistration"),
    ("company_collaboration", "CompanyCollaboration"),
    ("new_license_application", "NewLicenseApplication"),
    ("license_renewal_application", "LicenseApplication"),
    ("salesman_barman", "SalesmanBarmanModel"),
    ("special_permit", "SpecialPermitApplication"),
    ("distributor_permit", "DistributorPermitApplication"),
    ("distributor_permit", "IMFLRevalidation"),
    ("distributor_permit", "IMFLCancellation"),
)


def register_dashboard_cache_invalidation() -> None:
    for app_label, model_name in DASHBOARD_MODEL_LABELS:
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            continue

        post_save.connect(
            _invalidate_dashboard_counts,
            sender=model,
            dispatch_uid=f"dashboard_counts_post_save_{app_label}_{model_name}",
        )
        post_delete.connect(
            _invalidate_dashboard_counts,
            sender=model,
            dispatch_uid=f"dashboard_counts_post_delete_{app_label}_{model_name}",
        )


@receiver(post_save, sender=Transaction, dispatch_uid="dashboard_counts_transaction_post_save")
@receiver(post_delete, sender=Transaction, dispatch_uid="dashboard_counts_transaction_post_delete")
@receiver(post_save, sender=Objection, dispatch_uid="dashboard_counts_objection_post_save")
@receiver(post_delete, sender=Objection, dispatch_uid="dashboard_counts_objection_post_delete")
@receiver(post_save, sender=Rejection, dispatch_uid="dashboard_counts_rejection_post_save")
@receiver(post_delete, sender=Rejection, dispatch_uid="dashboard_counts_rejection_post_delete")
def _invalidate_dashboard_counts(sender, **kwargs):
    invalidate_dashboard_counts_cache()
