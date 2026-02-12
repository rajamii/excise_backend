from auth.workflow.models import StagePermission


def _normalize_token(value):
    return ''.join(ch for ch in str(value or '').lower() if ch.isalnum())


def has_workflow_access(user, workflow_id):
    if getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False):
        return True

    role = getattr(user, 'role', None)
    if not role:
        return False

    return StagePermission.objects.filter(
        role=role,
        can_process=True,
        stage__workflow_id=workflow_id
    ).exists()


def scope_by_profile_or_workflow(user, queryset, workflow_id, licensee_field='licensee_id'):
    # Licensee-style users are scoped to their own licensee_id.
    if hasattr(user, 'supply_chain_profile'):
        licensee_id = user.supply_chain_profile.licensee_id
        return queryset.filter(**{licensee_field: licensee_id})

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
