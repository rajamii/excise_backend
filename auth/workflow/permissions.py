from rest_framework import permissions
from .models import StagePermission

class HasStagePermission(permissions.BasePermission):
    def has_permission(self, request, view):
        # === 1. ALLOW ALL POST on /apply/ or /create/ (Licensee submission) ===
        if request.method == 'POST':
            path = request.path.lower()
            if '/apply/' in path or '/create/' in path:
                print("[HasStagePermission] Allowing POST on /apply/ or /create/")
                return True

        # === 2. Try to get application from view (detail, advance, etc.) ===
        get_object = getattr(view, 'get_object', None)
        if get_object:
            try:
                application = get_object()
                stage = getattr(application, 'current_stage', None)
                if stage and request.user.role:
                    return StagePermission.objects.filter(
                        stage=stage,
                        role=request.user.role,
                        can_process=True
                    ).exists()
            except (AttributeError, Exception):
                pass  # Continue to next checks

        # === 3. Check kwargs for application_id (e.g., advance, detail) ===
        app_id = (
            view.kwargs.get("application_id") or
            view.kwargs.get("pk") or
            getattr(view, 'application_id', None)
        )

        if app_id and request.method in ['GET', 'POST', 'PUT', 'PATCH']:
            print(f"[HasStagePermission] Allowing {request.method} for app_id={app_id}")
            return True

        # === 4. Default: deny ===
        print(f"[HasStagePermission] DENIED: method={request.method}, path={request.path}")
        return False