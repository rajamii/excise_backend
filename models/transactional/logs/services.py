import logging
from django.db import transaction
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from .models import AdminLog

logger = logging.getLogger(__name__)


def _truncate(val, max_len):
    if val is None:
        return None
    s = str(val)
    if len(s) > max_len:
        return s[:max_len]
    return s

# Canonical map of model class / app names to user-facing module names
MODULE_NAME_MAP = {
    # Supply Chain
    'enarequisitiondetail': 'ENA Bulk Requisition',
    'enarevalidationdetail': 'ENA Revalidation',
    'enacancellationdetail': 'ENA Cancellation',
    'enatransitpermitdetail': 'ENA Transit Permit',
    'hologramprocurement': 'Hologram Procurement',
    'hologramrequest': 'Hologram Request',
    'imflhologramprocurement': 'Hologram Procurement',
    'imflrevalidation': 'ENA Revalidation',
    'imflcancellation': 'ENA Cancellation',
    'bulkspirit': 'Bulk Spirit',
    'bulkspiritusage': 'Bulk Spirit Usage',
    'brandwarehouse': 'Brand Warehouse',
    'dailyhologramregister': 'Daily Hologram Register',
    'hologramserialrange': 'Hologram Serial Range',

    # Company
    'companyregistration': 'Company Registration',
    'companycollaboration': 'Company Collaboration',
    'companymodel': 'Company Management',

    # License
    'newlicenseapplication': 'New License Application',
    'licenseapplication': 'License Application',
    'licenserenewalapplication': 'License Renewal',
    'license': 'License Master',

    # Personnel & Permits
    'salesmanbarmanmodel': 'Salesman/Barman Registration',
    'specialpermitapplication': 'Dry Day Permit',
    'distributorpermitapplication': 'Distributor Permit',
    'labelregistration': 'Label Registration',
    'siteenquiryreport': 'Site Enquiry',
    'preventiveraid': 'Preventive Raids',
}


def _get_client_ip(request):
    if not request:
        return None
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def _get_user_agent(request):
    if not request:
        return None
    return request.META.get('HTTP_USER_AGENT', '')


def _resolve_user_snapshot(user=None, request=None, explicit_user_info=None):
    """
    Resolves snapshot data (admin_id, username, full_name, role, user_instance)
    reliably even if the user is anonymous, a dict, or system.
    """
    user_obj = None
    admin_id = None
    username = 'SYSTEM'
    full_name = 'System Action'
    role = 'SYSTEM'

    if explicit_user_info and isinstance(explicit_user_info, dict):
        admin_id = str(explicit_user_info.get('id') or explicit_user_info.get('admin_id') or '') or None
        username = str(explicit_user_info.get('username') or username)
        full_name = str(explicit_user_info.get('full_name') or explicit_user_info.get('name') or full_name)
        role = str(explicit_user_info.get('role') or role)

    if user and getattr(user, 'is_authenticated', False):
        user_obj = user
    elif request and getattr(request, 'user', None) and getattr(request.user, 'is_authenticated', False):
        user_obj = request.user

    if user_obj:
        admin_id = str(user_obj.pk)
        username = user_obj.username or user_obj.email or f"user_{user_obj.pk}"
        
        # Build human-friendly full name
        f_name = str(getattr(user_obj, 'first_name', '') or '').strip()
        l_name = str(getattr(user_obj, 'last_name', '') or '').strip()
        name_parts = [p for p in [f_name, l_name] if p]
        if name_parts:
            full_name = " ".join(name_parts)
        else:
            full_name = username

        # Role / Designation resolution
        role_rel = getattr(user_obj, 'role', None)
        if role_rel and hasattr(role_rel, 'name'):
            role = str(role_rel.name).strip()
        elif getattr(user_obj, 'is_superuser', False):
            role = 'Super Admin'
        elif getattr(user_obj, 'is_staff', False):
            role = 'Staff Admin'
        else:
            role = 'User'

    return {
        'user_obj': user_obj,
        'admin_id': admin_id,
        'username': username,
        'full_name': full_name,
        'role': role
    }


def _resolve_application_metadata(application=None, module_name=None, application_id=None):
    """
    Extracts module_name, application_id, content_type, and object_id from the application instance.
    """
    resolved_module = module_name or 'General Module'
    resolved_app_id = application_id or ''
    content_type = None
    object_id = None

    if application:
        try:
            content_type = ContentType.objects.get_for_model(application)
            object_id = str(application.pk)
        except Exception:
            pass

        model_name_lower = application.__class__.__name__.lower()
        if not module_name:
            resolved_module = MODULE_NAME_MAP.get(
                model_name_lower,
                application.__class__._meta.verbose_name.title() if hasattr(application, '_meta') else model_name_lower.replace('_', ' ').title()
            )

        if not application_id:
            for attr in ['application_id', 'reference_no', 'ref_no', 'application_no', 'requisition_no', 'permit_number', 'id', 'pk']:
                val = getattr(application, attr, None)
                if val:
                    resolved_app_id = str(val)
                    break

    return resolved_module, resolved_app_id, content_type, object_id


def resolve_stage_recipients(target_stage=None, target_stage_name=None, username_str=None, user_id_str=None, full_name_str=None, district=None):
    """
    Resolves all eligible recipient admin users for a target workflow stage/role.
    Returns a list of dicts: [{'id': str, 'username': str, 'full_name': str, 'role': str}]
    """
    recipients = []
    seen_ids = set()

    # 1. If explicit comma-separated or single usernames/user_ids provided
    if username_str:
        unames = [u.strip() for u in str(username_str).split(',') if u.strip()]
        for un in unames:
            try:
                from django.contrib.auth import get_user_model
                u = get_user_model().objects.filter(username=un).first()
                if u:
                    if str(u.pk) not in seen_ids:
                        seen_ids.add(str(u.pk))
                        fn = f"{getattr(u, 'first_name', '') or ''} {getattr(u, 'last_name', '') or ''}".strip() or u.username
                        recipients.append({
                            'id': str(u.pk),
                            'username': u.username,
                            'full_name': fn,
                            'role': getattr(getattr(u, 'role', None), 'name', '') or ''
                        })
                else:
                    if un not in seen_ids:
                        seen_ids.add(un)
                        recipients.append({
                            'id': user_id_str or '',
                            'username': un,
                            'full_name': full_name_str or un,
                            'role': ''
                        })
            except Exception:
                pass

    # 2. If stage/stage_name is available, also find all active admins for that stage role
    stage_text = target_stage_name or target_stage
    if stage_text:
        alias_map = [
            (['joint commissioner', 'jc'], 'Joint commissioner'),
            (['deputy commissioner', 'dc'], 'Deputy Commissioner'),
            (['commissioner', 'excise commissioner'], 'Commissioner'),
            (['oic', 'officer in charge', 'offcier in charge'], 'Offcier-In-Charge'),
            (['site inquiry', 'site enquiry', 'inquiry officer', 'enquiry officer'], 'Site Inquiry Officer'),
            (['permit section', 'permit'], 'Permit Section'),
            (['secretary'], 'Secretary'),
            (['district user', 'district'], 'District User'),
            (['factory admin', 'factory'], 'Factory Admin'),
            (['licensee'], 'Licensee'),
            (['distributor'], 'Distributor'),
            (['it cell', 'itcell'], 'IT Cell'),
            (['single window'], 'Single Window'),
        ]
        try:
            from auth.workflow.models import Role, WorkflowStage, StagePermission
            from django.contrib.auth import get_user_model
            User = get_user_model()

            roles = set()
            st_obj = WorkflowStage.objects.filter(name__iexact=str(stage_text)).first()
            if not st_obj and target_stage:
                st_obj = WorkflowStage.objects.filter(name__iexact=str(target_stage)).first()
            if st_obj:
                for sp in StagePermission.objects.filter(stage=st_obj, can_process=True).select_related('role'):
                    if sp.role:
                        roles.add(sp.role)
            
            if not roles:
                t_clean = ' '.join(str(stage_text).lower().replace('_', ' ').split())
                all_roles = list(Role.objects.all())
                for aliases, target_role_name in alias_map:
                    if any(alias in t_clean for alias in aliases):
                        matched = next((r for r in all_roles if r.name.lower() == target_role_name.lower()), None)
                        if matched:
                            roles.add(matched)
                            break
            
            for r in roles:
                qs = User.objects.filter(role=r, is_active=True)
                if district and qs.filter(district=district).exists():
                    qs = qs.filter(district=district)
                for u in qs:
                    if str(u.pk) not in seen_ids:
                        seen_ids.add(str(u.pk))
                        fn = f"{getattr(u, 'first_name', '') or ''} {getattr(u, 'last_name', '') or ''}".strip() or u.username
                        recipients.append({
                            'id': str(u.pk),
                            'username': u.username,
                            'full_name': fn,
                            'role': getattr(getattr(u, 'role', None), 'name', str(r.name))
                        })
        except Exception:
            pass

    return recipients


class AdminLogService:
    @staticmethod
    def log(
        action: str,
        user=None,
        request=None,
        application=None,
        module_name=None,
        application_id=None,
        from_stage=None,
        to_stage=None,
        to_stage_user_id=None,
        to_stage_username=None,
        to_stage_full_name=None,
        to_stage_name=None,
        to_stage_recipients=None,
        status=None,
        remarks=None,
        reverted_by=None,
        reverted_to=None,
        reverted_to_stage=None,
        ip_address=None,
        user_agent=None,
        metadata=None,
        timestamp=None,
        explicit_user_info=None,
    ) -> AdminLog:
        """
        Records a comprehensive audit log entry in the admin_log table.
        Guaranteed not to crash caller execution if an unexpected error occurs.
        """
        try:
            # 1. Resolve User Snapshot
            user_snap = _resolve_user_snapshot(user=user, request=request, explicit_user_info=explicit_user_info)

            # 2. Resolve Module & Application Info
            res_module, res_app_id, content_type, object_id = _resolve_application_metadata(
                application=application,
                module_name=module_name,
                application_id=application_id
            )

            # 3. Resolve Stage Names
            str_from_stage = getattr(from_stage, 'name', from_stage) if from_stage else None
            str_to_stage = getattr(to_stage, 'name', to_stage) if to_stage else None
            str_rev_to_stage = getattr(reverted_to_stage, 'name', reverted_to_stage) if reverted_to_stage else None

            final_to_stage_name = to_stage_name or (
                getattr(to_stage, 'description', None) or str_to_stage if to_stage else None
            )

            # 4. Resolve IP & User Agent
            final_ip = ip_address or _get_client_ip(request)
            final_ua = user_agent or _get_user_agent(request)

            # 5. Resolve Revert Details (if action is REVERT or revert fields passed)
            reverted_by_id = None
            reverted_by_username = None
            reverted_by_name = None
            reverted_by_role = None

            reverted_to_id = None
            reverted_to_username = None
            reverted_to_name = None
            reverted_to_role = None

            action_upper = str(action or 'ACTION').strip().upper()

            if action_upper == 'REVERT' or reverted_by or reverted_to:
                # Reverted By
                if reverted_by:
                    rev_by_snap = _resolve_user_snapshot(user=reverted_by)
                    reverted_by_id = rev_by_snap['admin_id']
                    reverted_by_username = rev_by_snap['username']
                    reverted_by_name = rev_by_snap['full_name']
                    reverted_by_role = rev_by_snap['role']
                else:
                    reverted_by_id = user_snap['admin_id']
                    reverted_by_username = user_snap['username']
                    reverted_by_name = user_snap['full_name']
                    reverted_by_role = user_snap['role']

                # Reverted To
                if reverted_to:
                    if hasattr(reverted_to, 'name') and not hasattr(reverted_to, 'username'):
                        # Role instance or stage
                        reverted_to_role = str(reverted_to.name)
                        reverted_to_name = str(reverted_to.name)
                    elif getattr(reverted_to, 'is_authenticated', False) or hasattr(reverted_to, 'username'):
                        rev_to_snap = _resolve_user_snapshot(user=reverted_to)
                        reverted_to_id = rev_to_snap['admin_id']
                        reverted_to_username = rev_to_snap['username']
                        reverted_to_name = rev_to_snap['full_name']
                        reverted_to_role = rev_to_snap['role']
                    elif isinstance(reverted_to, dict):
                        reverted_to_id = str(reverted_to.get('id') or '') or None
                        reverted_to_username = str(reverted_to.get('username') or '') or None
                        reverted_to_name = str(reverted_to.get('name') or reverted_to.get('full_name') or '') or None
                        reverted_to_role = str(reverted_to.get('role') or '') or None
                    else:
                        reverted_to_role = str(reverted_to)
                        reverted_to_name = str(reverted_to)

                if not str_rev_to_stage and str_to_stage:
                    str_rev_to_stage = str_to_stage

            final_to_stage_username = to_stage_username
            final_to_stage_user_id = to_stage_user_id
            final_to_stage_full_name = to_stage_full_name

            if not final_to_stage_username and action_upper == 'REVERT':
                final_to_stage_username = reverted_to_username or reverted_to_role
                if not final_to_stage_user_id:
                    final_to_stage_user_id = reverted_to_id
                if not final_to_stage_full_name:
                    final_to_stage_full_name = reverted_to_name

            # Resolve multiple recipients if provided or derive from stage
            final_recipients = to_stage_recipients or []
            if not final_recipients and (str_to_stage or final_to_stage_name or final_to_stage_username):
                app_district = getattr(application, 'district', None)
                final_recipients = resolve_stage_recipients(
                    target_stage=str_to_stage,
                    target_stage_name=final_to_stage_name,
                    username_str=final_to_stage_username,
                    user_id_str=final_to_stage_user_id,
                    full_name_str=final_to_stage_full_name,
                    district=app_district
                )

            if final_recipients:
                if not final_to_stage_user_id:
                    final_to_stage_user_id = ", ".join([str(r['id']) for r in final_recipients if r.get('id')])
                if not final_to_stage_username:
                    final_to_stage_username = ", ".join([r['username'] for r in final_recipients if r.get('username')])
                if not final_to_stage_full_name:
                    final_to_stage_full_name = ", ".join([r['full_name'] for r in final_recipients if r.get('full_name')])
            elif final_to_stage_username and (not final_to_stage_user_id or not final_to_stage_full_name):
                try:
                    from django.contrib.auth import get_user_model
                    target_u = get_user_model().objects.filter(username=final_to_stage_username).first()
                    if target_u:
                        if not final_to_stage_user_id:
                            final_to_stage_user_id = str(target_u.pk)
                        if not final_to_stage_full_name:
                            f_n = str(getattr(target_u, 'first_name', '') or '').strip()
                            l_n = str(getattr(target_u, 'last_name', '') or '').strip()
                            n_p = [p for p in [f_n, l_n] if p]
                            final_to_stage_full_name = " ".join(n_p) if n_p else (target_u.username or getattr(target_u, 'email', None))
                except Exception:
                    pass

            meta_payload = dict(metadata or {})
            if final_recipients:
                meta_payload['forwarded_recipients'] = final_recipients

            # 6. Create AdminLog inside a savepoint so any logging failure never aborts outer transaction
            with transaction.atomic():
                log_entry = AdminLog.objects.create(
                    admin_id=_truncate(user_snap.get('admin_id'), 100),
                    username=_truncate(user_snap.get('username'), 150) or 'SYSTEM',
                    full_name=_truncate(user_snap.get('full_name'), 255) or 'System Action',
                    role=_truncate(user_snap.get('role'), 100) or 'SYSTEM',
                    user=user_snap.get('user_obj'),
                    module_name=_truncate(res_module, 150),
                    application_id=_truncate(res_app_id, 150),
                    content_type=content_type,
                    object_id=_truncate(object_id, 255),
                    action=_truncate(action_upper, 100),
                    from_stage=_truncate(str(str_from_stage) if str_from_stage else None, 150),
                    to_stage=_truncate(str(str_to_stage) if str_to_stage else None, 150),
                    to_stage_name=_truncate(str(final_to_stage_name) if final_to_stage_name else None, 255),
                    to_stage_user_id=_truncate(str(final_to_stage_user_id) if final_to_stage_user_id else None, 100),
                    to_stage_username=_truncate(str(final_to_stage_username) if final_to_stage_username else None, 150),
                    to_stage_full_name=_truncate(str(final_to_stage_full_name) if final_to_stage_full_name else None, 255),
                    status=_truncate(status or f"Action {action_upper} Completed", 100),
                    remarks=remarks or "",
                    reverted_by_id=_truncate(reverted_by_id, 100),
                    reverted_by_username=_truncate(reverted_by_username, 150),
                    reverted_by_name=_truncate(reverted_by_name, 255),
                    reverted_by_role=_truncate(reverted_by_role, 100),
                    reverted_to_id=_truncate(reverted_to_id, 100),
                    reverted_to_username=_truncate(reverted_to_username, 150),
                    reverted_to_name=_truncate(reverted_to_name, 255),
                    reverted_to_role=_truncate(reverted_to_role, 100),
                    reverted_to_stage=_truncate(str(str_rev_to_stage) if str_rev_to_stage else None, 150),
                    ip_address=final_ip,
                    user_agent=final_ua,
                    metadata=meta_payload,
                    timestamp=timestamp or timezone.now()
                )
                return log_entry

        except Exception as e:
            logger.error("Failed to write to admin_log: %s", e, exc_info=True)
            return None


def log_admin_action(*args, **kwargs):
    """
    Convenience global function to log admin actions.
    """
    return AdminLogService.log(*args, **kwargs)

