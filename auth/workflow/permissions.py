from rest_framework import permissions
from .models import StagePermission

class HasStagePermission(permissions.BasePermission):
    """
    Allows access only if the user's role has can_process=True
    on the application's CURRENT stage (i.e., the stage they're acting FROM).
    """
    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated or not getattr(user, 'role', None):
            return False

        def normalized_role_token() -> str:
            raw = getattr(user.role, 'name', '') or ''
            token = ''.join(ch for ch in str(raw).lower() if ch.isalnum())
            aliases = {
                'licenseuser': 'licensee',
                'licenseeuser': 'licensee',
                'licencee': 'licensee',
            }
            return aliases.get(token, token)

        # Allow licensee to resolve objections even if no StagePermission exists on the Objection stage.
        # The WorkflowService enforces that only the licensee can resolve objections.
        if request.method in ['POST', 'PUT', 'PATCH'] and '/resolve-objections/' in request.path:
            return normalized_role_token() == 'licensee'

        # 1. Allow licensee to submit new applications
        if request.method == 'POST' and any(path in request.path for path in ['/apply/', '/create/']):
            return getattr(user.role, 'id', None) == 2

        # 2. For advance, raise-objection, resolve-objection, etc.
        if request.method in ['POST', 'PUT', 'PATCH']:
            # Try to get application from view (safest)
            application = None
            if hasattr(view, 'get_object'):
                try:
                    application = view.get_object()
                except (AttributeError, AssertionError):
                    pass

            # Fallback: extract from kwargs and resolve polymorphically
            if not application:
                app_id = view.kwargs.get('application_id') or view.kwargs.get('pk')
                if app_id:
                    from .services import WorkflowService
                    try:
                        application = WorkflowService.get_application_by_id(app_id)
                    except:
                        return False

            if application and user.role:
                return StagePermission.objects.filter(
                    stage=application.current_stage,
                    role=user.role,
                    can_process=True
                ).exists()

        return True
