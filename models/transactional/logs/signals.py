import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_logged_out
from .models import UserActivity, AdminLog
from .middleware import get_current_request
from .services import MODULE_NAME_MAP, log_crud_action

logger = logging.getLogger(__name__)
User = get_user_model()

# Apps / models to monitor for Admin CRUD activity
AUDIT_APP_LABELS = {
    'core', 'license', 'supply_chain', 'liquor_data',
    'transit_permit', 'vehicles', 'about_us', 'contact_us',
    'notification', 'preventive_raids', 'company_collaboration',
    'user', 'roles', 'wallet'
}

# Explicit models to ignore from automatic signal logging to prevent noise or recursion
IGNORED_MODELS = {
    'adminlog', 'useractivity', 'session', 'logentry', 'contenttype',
    'permission', 'migraterecorder', 'token', 'authtoken'
}


def _resolve_instance_descriptors(instance):
    model_name_lower = instance.__class__.__name__.lower()
    module_name = MODULE_NAME_MAP.get(
        model_name_lower,
        instance._meta.verbose_name.title() if hasattr(instance, '_meta') else model_name_lower.replace('_', ' ').title()
    )
    target_id = str(getattr(instance, 'pk', '') or getattr(instance, 'id', '') or '')
    target_name = (
        getattr(instance, 'name', None)
        or getattr(instance, 'username', None)
        or getattr(instance, 'title', None)
        or getattr(instance, 'license_id', None)
        or getattr(instance, 'application_id', None)
        or getattr(instance, 'establishment_name', None)
        or getattr(instance, 'description', None)
        or getattr(instance, 'code', None)
        or str(instance)
    )
    return module_name, target_id, str(target_name)


@receiver(post_save, sender=User)
def track_registration(sender, instance, created, **kwargs):
    if created:
        UserActivity.objects.create(
            user=instance,
            activity_type=UserActivity.ActivityType.REGISTRATION,
            metadata={
                'registration_method': 'email',
                'initial_source': kwargs.get('source', 'direct')
            }
        )


@receiver(user_logged_in)
def track_login(sender, request, user, **kwargs):
    UserActivity.objects.create(
        user=user,
        activity_type=UserActivity.ActivityType.LOGIN,
        ip_address=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT'),
        metadata={
            'auth_method': kwargs.get('backend', 'email'),
            'session_id': getattr(request.session, 'session_key', None)
        }
    )


@receiver(user_logged_out)
def track_logout(sender, request, user, **kwargs):
    if not user or not getattr(user, 'is_authenticated', False):
        return
    UserActivity.objects.create(
        user=user,
        activity_type=UserActivity.ActivityType.LOGOUT,
        ip_address=get_client_ip(request),
        metadata={
            'session_id': getattr(getattr(request, 'session', None), 'session_key', None)
        }
    )


@receiver(post_save)
def track_admin_master_crud_save(sender, instance, created, **kwargs):
    # Avoid recursion or logging internal log tables
    model_name_lower = sender.__name__.lower()
    if model_name_lower in IGNORED_MODELS or isinstance(instance, (AdminLog, UserActivity)):
        return

    # Check if instance already handled by a dedicated view
    if getattr(instance, '_admin_log_handled', False):
        return

    # Only log if requested via active HTTP request by an authenticated user
    request = get_current_request()
    if not request or not hasattr(request, 'user') or not getattr(request.user, 'is_authenticated', False):
        return

    app_label = instance._meta.app_label if hasattr(instance, '_meta') else ''
    if app_label not in AUDIT_APP_LABELS and 'master' not in app_label.lower() and 'user' not in app_label.lower():
        return

    # Don't auto-log transactional applications that use workflow advancement (they log through workflow services)
    if model_name_lower in ('newlicenseapplication', 'licenseapplication', 'licenserenewalapplication', 'enarequisitiondetail', 'enarevalidationdetail', 'enacancellationdetail'):
        return

    try:
        module_name, target_id, target_name = _resolve_instance_descriptors(instance)
        action = "CREATE" if created else "UPDATE"

        meta = {
            'model': sender.__name__,
            'app_label': app_label,
            'pk': target_id,
            'target_name': target_name,
        }

        log_crud_action(
            action=action,
            user=request.user,
            request=request,
            module_name=module_name,
            target_id=target_id,
            target_name=target_name,
            metadata=meta
        )
    except Exception as exc:
        logger.debug("Automatic audit logging skipped for %s: %s", sender.__name__, exc)


@receiver(post_delete)
def track_admin_master_crud_delete(sender, instance, **kwargs):
    model_name_lower = sender.__name__.lower()
    if model_name_lower in IGNORED_MODELS or isinstance(instance, (AdminLog, UserActivity)):
        return

    if getattr(instance, '_admin_log_handled', False):
        return

    request = get_current_request()
    if not request or not hasattr(request, 'user') or not getattr(request.user, 'is_authenticated', False):
        return

    app_label = instance._meta.app_label if hasattr(instance, '_meta') else ''
    if app_label not in AUDIT_APP_LABELS and 'master' not in app_label.lower() and 'user' not in app_label.lower():
        return

    if model_name_lower in ('newlicenseapplication', 'licenseapplication', 'licenserenewalapplication'):
        return

    try:
        module_name, target_id, target_name = _resolve_instance_descriptors(instance)
        meta = {
            'model': sender.__name__,
            'app_label': app_label,
            'pk': target_id,
            'target_name': target_name,
        }
        log_crud_action(
            action="DELETE",
            user=request.user,
            request=request,
            module_name=module_name,
            target_id=target_id,
            target_name=target_name,
            metadata=meta
        )
    except Exception as exc:
        logger.debug("Automatic audit logging delete skipped for %s: %s", sender.__name__, exc)


def get_client_ip(request):
    if not request:
        return None
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip
