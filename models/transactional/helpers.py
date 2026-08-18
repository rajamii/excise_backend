from auth.workflow.models import WorkflowStage, WorkflowTransition
import re

def _normalize_role(role_name):
    if not role_name:
        return None
    normalized = str(role_name).strip().lower().replace('-', '_').replace(' ', '_')
    aliases = {
        'license_user': 'licensee',
        'licensee_user': 'licensee',
        'singlewindow': 'single_window',
        'siteadmin': 'site_admin',
        'distributor': 'licensee',
    }
    return aliases.get(normalized, normalized)

def _collect_reachable_stage_names(workflow_id: int, start_stage_names: set[str]):
    if not start_stage_names:
        return set()

    edges = {}
    for from_name, to_name in WorkflowTransition.objects.filter(workflow_id=workflow_id).values_list(
        'from_stage__name', 'to_stage__name'
    ):
        edges.setdefault(from_name, set()).add(to_name)

    visited = set(start_stage_names)
    stack = list(start_stage_names)
    while stack:
        current = stack.pop()
        for nxt in edges.get(current, set()):
            if nxt not in visited:
                visited.add(nxt)
                stack.append(nxt)
    return visited

def _extract_level_index(stage_name):
    if not stage_name:
        return None
    match = re.match(r'^level_(\d+)$', str(stage_name).strip().lower())
    return int(match.group(1)) if match else None


def _get_stage_sets(workflow_id: int):
    stages = WorkflowStage.objects.filter(workflow_id=workflow_id)
    stage_names = set(stages.values_list('name', flat=True))
    level_stage_names = sorted(
        [name for name in stage_names if _extract_level_index(name) is not None],
        key=lambda name: _extract_level_index(name) or 0
    )
    level_indexes = {name: _extract_level_index(name) for name in level_stage_names}
    objection_stage_names = {name for name in stage_names if 'objection' in str(name).lower()}
    rejected_stage_names = {name for name in stage_names if 'rejected' in str(name).lower()}
    approved_stage_names = {
        stage.name for stage in stages
        if stage.is_final and 'rejected' not in stage.name.lower()
    }
    approved_stage_names.update({name for name in stage_names if 'approved' in str(name).lower()})
    payment_stage_names = {name for name in stage_names if 'payment' in str(name).lower()}
    initial_stage_names = set(stages.filter(is_initial=True).values_list('name', flat=True))

    return {
        'all': stage_names,
        'level': set(level_stage_names),
        'level_ordered': level_stage_names,
        'level_indexes': level_indexes,
        'objection': objection_stage_names,
        'rejected': rejected_stage_names,
        'approved': approved_stage_names,
        'payment': payment_stage_names,
        'initial': initial_stage_names,
    }

def _get_role_stage_names(user, workflow_id: int):
    role = getattr(user, 'role', None)
    if not role:
        return set()
    return set(
        WorkflowStage.objects.filter(
            workflow_id=workflow_id,
            stagepermission__role=role,
            stagepermission__can_process=True
        ).values_list('name', flat=True).distinct()
    )

def _is_district_scoped_role(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    role_id = getattr(user, 'role_id', None) or getattr(getattr(user, 'role', None), 'id', None)
    if role_id in [4, 8]:
        return True
    role_name = _normalize_role(getattr(getattr(user, 'role', None), 'name', None))
    return role_name in [
        'district_user', 'district_collector', 'district_admin',
        'sub_enquiry_officer', 'site_inquiry_officer', 'site_enquiry_officer', 'site_inquiry'
    ]

def _get_user_district_code(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return None
    district_obj = getattr(user, 'district', None)
    if district_obj:
        code = getattr(district_obj, 'district_code', None) or getattr(district_obj, 'pk', None)
        if code:
            return code
    return getattr(user, 'district_id', None)

def _filter_by_user_district(qs, user, primary_field=None):
    if not _is_district_scoped_role(user):
        return qs
    district_code = _get_user_district_code(user)
    if not district_code:
        return qs.none()

    from django.db.models import Q
    model_fields = [f.name for f in qs.model._meta.get_fields()]

    possible_fields = []
    if primary_field:
        possible_fields.append(primary_field)
    possible_fields.extend(['site_district', 'excise_district', 'district'])

    q_filter = Q()
    matched = False
    for field_name in possible_fields:
        if field_name in model_fields:
            q_filter |= (
                Q(**{f"{field_name}__district_code": district_code}) |
                Q(**{f"{field_name}_id": district_code}) |
                Q(**{f"{field_name}__id": district_code})
            )
            matched = True
            break

    if 'applicant' in model_fields:
        q_filter |= (
            Q(applicant__district__district_code=district_code) |
            Q(applicant__district_id=district_code)
        )
        matched = True

    if 'license' in model_fields:
        q_filter |= (
            Q(license__excise_district__district_code=district_code) |
            Q(license__excise_district_id=district_code)
        )
        matched = True

    if 'old_license' in model_fields:
        q_filter |= (
            Q(old_license__excise_district__district_code=district_code) |
            Q(old_license__excise_district_id=district_code)
        )
        matched = True

    if not matched and primary_field:
        q_filter = (
            Q(**{f"{primary_field}__district_code": district_code}) |
            Q(**{f"{primary_field}_id": district_code})
        )

    return qs.filter(q_filter).distinct()