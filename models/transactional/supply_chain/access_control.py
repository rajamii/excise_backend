from auth.workflow.models import StagePermission, WorkflowTransition
from models.masters.license.models import License
from django.contrib.contenttypes.models import ContentType
from models.transactional.new_license_application.models import NewLicenseApplication


def _normalize_token(value):
    return ''.join(ch for ch in str(value or '').lower() if ch.isalnum())


def has_workflow_access(user, workflow_id):
    if getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False):
        return True

    role = getattr(user, 'role', None)
    if not role:
        return False

    if StagePermission.objects.filter(
        role=role,
        can_process=True,
        stage__workflow_id=workflow_id
    ).exists():
        return True

    # Dynamic DB-driven fallback:
    # If StagePermission is not seeded, infer workflow access from
    # WorkflowTransition.condition role/role_id mappings.
    role_id = getattr(role, 'id', None)
    role_token = _normalize_token(getattr(role, 'name', ''))
    transition_conditions = WorkflowTransition.objects.filter(
        workflow_id=workflow_id
    ).values_list('condition', flat=True)

    for cond in transition_conditions:
        if not isinstance(cond, dict):
            continue

        cond_role_id = cond.get('role_id')
        if cond_role_id is not None and role_id is not None:
            try:
                if int(cond_role_id) == int(role_id):
                    return True
            except (TypeError, ValueError):
                pass

        cond_role_token = _normalize_token(cond.get('role'))
        if cond_role_token and role_token and cond_role_token == role_token:
            return True

    return False


def scope_by_profile_or_workflow(user, queryset, workflow_id, licensee_field='licensee_id'):
    # Licensee-style users are scoped to their own licensee_id.
    scoped_values = set()

    if hasattr(user, 'supply_chain_profile'):
        licensee_id = user.supply_chain_profile.licensee_id
        if licensee_id:
            scoped_values.add(str(licensee_id))

    # Fallback: users with mapped manufacturing units but no active supply-chain profile
    # should still see their own records.
    if hasattr(user, 'manufacturing_units'):
        unit_licensee_ids = list(
            user.manufacturing_units.exclude(licensee_id__isnull=True)
            .exclude(licensee_id='')
            .values_list('licensee_id', flat=True)
        )
        for value in unit_licensee_ids:
            scoped_values.add(str(value))

    # Include formal license IDs (e.g., NA/1101/2025-26/0001) issued to this user.
    qs_by_applicant = License.objects.filter(applicant=user, is_active=True)

    # Compatibility fallback: match license by source_object_id from user's new applications,
    # same style as MyLicensesListView.
    try:
        new_app_ct = ContentType.objects.get_for_model(NewLicenseApplication)
        user_app_ids = NewLicenseApplication.objects.filter(
            applicant=user
        ).values_list('application_id', flat=True)
        qs_by_source_object = License.objects.filter(
            source_content_type=new_app_ct,
            source_object_id__in=user_app_ids,
            is_active=True
        )
        license_qs = (qs_by_applicant | qs_by_source_object).distinct()
    except Exception:
        license_qs = qs_by_applicant

    license_ids = list(
        license_qs.exclude(license_id__isnull=True)
        .exclude(license_id='')
        .values_list('license_id', flat=True)
    )
    for value in license_ids:
        scoped_values.add(str(value))

    if scoped_values:
        return queryset.filter(**{f'{licensee_field}__in': list(scoped_values)})

    # Workflow roles use DB-configured stage permissions.
    if has_workflow_access(user, workflow_id):
        return queryset

    return queryset.none()


def condition_role_matches(cond, user):
    cond = cond or {}
    role_id = getattr(user, 'role_id', None)
    cond_role_id = cond.get('role_id')
    if cond_role_id is not None:
        if role_id is None:
            return False
        try:
            return int(cond_role_id) == int(role_id)
        except (TypeError, ValueError):
            return False

    cond_role = _normalize_token(cond.get('role'))
    if not cond_role:
        return True

    user_role = _normalize_token(getattr(getattr(user, 'role', None), 'name', ''))
    return cond_role == user_role


def transition_matches(transition, user, action):
    cond = transition.condition or {}
    cond_action = str(cond.get('action') or '').upper()
    if cond_action and cond_action != str(action or '').upper():
        return False
    return condition_role_matches(cond, user)
