from auth.workflow.models import StagePermission, WorkflowTransition
from models.masters.license.models import License
from django.contrib.contenttypes.models import ContentType
from models.transactional.new_license_application.models import NewLicenseApplication


def _normalize_token(value):
    return ''.join(ch for ch in str(value or '').lower() if ch.isalnum())


def _role_token_matches_cond(user_role_token, cond_role_token):
    user_role_token = _normalize_token(user_role_token)
    cond_role_token = _normalize_token(cond_role_token)
    if not cond_role_token:
        return True
    if user_role_token == cond_role_token:
        return True

    officer_aliases = {
        'officer', 'officerincharge', 'offcierincharge', 'oic',
        'level1', 'level2', 'level3', 'level4', 'level5', 'siteadmin'
    }
    if user_role_token in officer_aliases and cond_role_token in officer_aliases:
        return True

    return False


def _expand_license_aliases(value):
    normalized = str(value or '').strip()
    if not normalized:
        return []
    aliases = [normalized]
    if normalized.startswith('NLI/'):
        aliases.append(f"NA/{normalized[4:]}")
    elif normalized.startswith('NA/'):
        aliases.append(f"NLI/{normalized[3:]}")
    return aliases


def _is_oic_scoped_user(user):
    role_token = _normalize_token(getattr(getattr(user, 'role', None), 'name', ''))
    return (
        bool(getattr(user, 'is_oic_managed', False))
        or hasattr(user, 'oic_assignment')
        or role_token in {'officerincharge', 'offcierincharge', 'oic'}
    )


def _is_licensee_scoped_user(user):
    role_token = _normalize_token(getattr(getattr(user, 'role', None), 'name', ''))
    return role_token in {'licensee', 'licencee'}


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
        if cond_role_token and role_token and _role_token_matches_cond(role_token, cond_role_token):
            return True

    return False


def scope_by_profile_or_workflow(user, queryset, workflow_id, licensee_field='licensee_id'):
    # Licensee/OIC-style users are scoped by mapped license identifiers.
    scoped_values = set()

    is_oic_user = _is_oic_scoped_user(user)

    # OIC users must be scoped to mapped assignment/license IDs, not their own profile ID.
    if is_oic_user and hasattr(user, 'oic_assignment'):
        assignment = getattr(user, 'oic_assignment')
        mapped_values = [
            getattr(assignment, 'licensee_id', ''),
            getattr(getattr(assignment, 'license', None), 'license_id', ''),
            getattr(getattr(assignment, 'approved_application', None), 'application_id', ''),
        ]
        for raw_value in mapped_values:
            for alias in _expand_license_aliases(raw_value):
                scoped_values.add(alias)
    else:
        if hasattr(user, 'supply_chain_profile'):
            licensee_id = user.supply_chain_profile.licensee_id
            if licensee_id:
                for alias in _expand_license_aliases(licensee_id):
                    scoped_values.add(alias)

    # Fallback: users with mapped manufacturing units but no active supply-chain profile
    # should still see their own records.
    if hasattr(user, 'manufacturing_units'):
        unit_licensee_ids = list(
            user.manufacturing_units.exclude(licensee_id__isnull=True)
            .exclude(licensee_id='')
            .values_list('licensee_id', flat=True)
        )
        for value in unit_licensee_ids:
            for alias in _expand_license_aliases(value):
                scoped_values.add(alias)

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
        for alias in _expand_license_aliases(value):
            scoped_values.add(alias)

    if scoped_values:
        return queryset.filter(**{f'{licensee_field}__in': list(scoped_values)})

    # OIC users without an assignment should not see cross-license records.
    if is_oic_user:
        return queryset.none()

    # Licensee users without mapped IDs must not fall back to workflow-wide access.
    if _is_licensee_scoped_user(user):
        return queryset.none()

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
    return _role_token_matches_cond(user_role, cond_role)


def transition_matches(transition, user, action):
    cond = transition.condition or {}
    cond_action = str(cond.get('action') or '').upper()
    if cond_action and cond_action != str(action or '').upper():
        return False
    return condition_role_matches(cond, user)
