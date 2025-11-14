from rest_framework import permissions
from .models import StagePermission

class HasStagePermission(permissions.BasePermission):
    def has_permission(self, request, view):
        # === 1. ALLOW ALL POST /apply/ or /create/ (Licensee submission) ===
        if request.method == 'POST':
            path = request.path.lower()
            if '/apply/' in path or '/create/' in path:
                print("[HasStagePermission] Allowing POST on /apply/ or /create/")
                return True

        # === 2. Try to get application from view (detail, advance, etc.) ===
        application = getattr(view, 'get_object', lambda: None)()
        if application:
            stage = getattr(application, 'current_stage', None)
            if not stage:
                return False
            return StagePermission.objects.filter(
                stage=stage,
                role=request.user.role,
                can_process=True
            ).exists()

        # === 3. No application object: check kwargs for GET (list/detail) ===
        app_id = view.kwargs.get("application_id") or view.kwargs.get("pk")
        if app_id and request.method == 'GET':
            print(f"[HasStagePermission] Allowing GET for app_id={app_id}")
            return True

        # === 4. For POST without /apply/ (e.g. advance), require app_id ===
        if request.method == 'POST' and app_id:
            # Let it fall through to get_object() in view
            return True

        # === 5. Default: deny ===
        print(f"[HasStagePermission] DENIED: method={request.method}, path={request.path}")
        return False