import logging
from django.db.models.signals import pre_save, post_save, post_delete
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
    'user', 'roles', 'wallet', 'authentication'
}

# Explicit models to ignore from automatic signal logging to prevent noise or recursion
IGNORED_MODELS = {
    'adminlog', 'useractivity', 'session', 'logentry', 'contenttype',
    'permission', 'migraterecorder', 'token', 'authtoken', 'outstandingtoken', 'blacklistedtoken'
}


def _resolve_instance_descriptors(instance):
    model_name_lower = instance.__class__.__name__.lower()
    module_name = MODULE_NAME_MAP.get(
        model_name_lower,
        instance._meta.verbose_name.title() if hasattr(instance, '_meta') else model_name_lower.replace('_', ' ').title()
    )
    target_id = str(getattr(instance, 'pk', '') or getattr(instance, 'id', '') or '')
    target_name = (
        getattr(instance, 'district_name', None)
        or getattr(instance, 'subdivision_name', None)
        or getattr(instance, 'police_station_name', None)
        or getattr(instance, 'road_name', None)
        or getattr(instance, 'name', None)
        or getattr(instance, 'username', None)
        or getattr(instance, 'title', None)
        or getattr(instance, 'brand_name', None)
        or getattr(instance, 'license_id', None)
        or getattr(instance, 'application_id', None)
        or getattr(instance, 'establishment_name', None)
        or getattr(instance, 'description', None)
        or getattr(instance, 'code', None)
        or str(instance)
    )
    return module_name, target_id, str(target_name)


def _serialize_model_instance(instance):
    """Serializes model instance fields to a JSON-safe dictionary."""
    data = {}
    if not hasattr(instance, '_meta'):
        return data
    for field in instance._meta.fields:
        if field.name in ('password', '_state'):
            continue
        try:
            val = getattr(instance, field.name, None)
            if val is None:
                continue
            if hasattr(val, 'pk'):
                data[field.name] = str(val)
            elif hasattr(val, 'isoformat'):
                data[field.name] = val.isoformat()
            elif isinstance(val, (str, int, float, bool, list, dict)):
                data[field.name] = val
            else:
                data[field.name] = str(val)
        except Exception:
            continue
    return data


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


@receiver(pre_save)
def track_admin_master_crud_presave(sender, instance, **kwargs):
    """
    Snapshots existing database state before save occurs so exact field changes can be diffed.
    """
    model_name_lower = sender.__name__.lower()
    if model_name_lower in IGNORED_MODELS or isinstance(instance, (AdminLog, UserActivity)):
        return

    if not instance.pk:
        return  # New instance, will be captured in post_save as CREATE

    request = get_current_request()
    if not request or not hasattr(request, 'user') or not getattr(request.user, 'is_authenticated', False):
        return

    app_label = instance._meta.app_label if hasattr(instance, '_meta') else ''
    if app_label not in AUDIT_APP_LABELS and 'master' not in app_label.lower() and 'user' not in app_label.lower():
        return

    try:
        old_instance = sender.objects.filter(pk=instance.pk).first()
        if old_instance:
            instance._pre_save_snapshot = _serialize_model_instance(old_instance)
    except Exception:
        pass


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
        current_data = _serialize_model_instance(instance)

        if created:
            action = "CREATE"
            meta = {
                'action_type': 'CREATE',
                'module': module_name,
                'model': sender.__name__,
                'record_id': target_id,
                'record_name': target_name,
                'new_values': current_data,
                'summary': f"Created new {module_name} record '{target_name}'"
            }
            # Readable summary of main created fields
            highlight_keys = [k for k in current_data.keys() if k not in ('id', 'created_at', 'updated_at', 'created_by', 'updated_by')][:4]
            field_summary = ", ".join(f"{k.replace('_', ' ').title()}: {current_data[k]}" for k in highlight_keys)
            remarks = f"Created {module_name} '{target_name}' (ID: {target_id}). {field_summary}".strip()

            log_crud_action(
                action=action,
                user=request.user,
                request=request,
                module_name=module_name,
                target_id=target_id,
                target_name=target_name,
                remarks=remarks,
                metadata=meta
            )
        else:
            old_data = getattr(instance, '_pre_save_snapshot', {}) or {}
            diffs = []
            for f_name, new_val in current_data.items():
                if f_name in ('updated_at', 'last_login', 'modified_at'):
                    continue
                old_val = old_data.get(f_name)
                if old_val != new_val and str(old_val or '') != str(new_val or ''):
                    verbose_name = f_name.replace('_', ' ').title()
                    if hasattr(sender, '_meta'):
                        try:
                            f_field = sender._meta.get_field(f_name)
                            verbose_name = getattr(f_field, 'verbose_name', verbose_name).title()
                        except Exception:
                            pass
                    diffs.append({
                        'field': verbose_name,
                        'field_name': f_name,
                        'from': str(old_val) if old_val is not None else '',
                        'to': str(new_val) if new_val is not None else ''
                    })

            # Check if toggling active
            action = "UPDATE"
            if len(diffs) == 1 and diffs[0]['field_name'] in ('is_active', 'status', 'active'):
                action = "TOGGLE_ACTIVE"

            diff_summary_parts = [f"{d['field']}: '{d['from']}' → '{d['to']}'" for d in diffs]
            diff_text = "; ".join(diff_summary_parts) if diff_summary_parts else "Record saved with no field value differences."
            remarks = f"Updated {module_name} '{target_name}' (ID: {target_id}) | {diff_text}"

            meta = {
                'action_type': action,
                'module': module_name,
                'model': sender.__name__,
                'record_id': target_id,
                'record_name': target_name,
                'field_diffs': diffs,
                'fields_changed': [d['field'] for d in diffs],
                'old_values': {d['field_name']: d['from'] for d in diffs},
                'new_values': {d['field_name']: d['to'] for d in diffs},
                'summary': f"Updated {len(diffs)} field(s) on '{target_name}' in {module_name}"
            }

            log_crud_action(
                action=action,
                user=request.user,
                request=request,
                module_name=module_name,
                target_id=target_id,
                target_name=target_name,
                fields_changed=[d['field'] for d in diffs],
                old_data={d['field_name']: d['from'] for d in diffs},
                new_data={d['field_name']: d['to'] for d in diffs},
                remarks=remarks,
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
        deleted_data = _serialize_model_instance(instance)
        remarks = f"Deleted {module_name} record '{target_name}' (ID: {target_id})"

        meta = {
            'action_type': 'DELETE',
            'module': module_name,
            'model': sender.__name__,
            'record_id': target_id,
            'record_name': target_name,
            'deleted_values': deleted_data,
            'summary': f"Deleted '{target_name}' from {module_name}"
        }

        log_crud_action(
            action="DELETE",
            user=request.user,
            request=request,
            module_name=module_name,
            target_id=target_id,
            target_name=target_name,
            remarks=remarks,
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

