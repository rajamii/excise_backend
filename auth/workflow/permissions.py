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

        # 1. Allow licensee to submit new applications
        if request.method == 'POST' and any(path in request.path for path in ['/apply/', '/create/']):
            return user.role.name == 'licensee'

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