from functools import wraps
from rest_framework.exceptions import PermissionDenied
from django.http import JsonResponse
from rest_framework_simplejwt.authentication import JWTAuthentication
from .permissions import HasAppPermission, PermissionAction

def has_app_permission(app_label: str, action: PermissionAction):
    """
    Decorator that applies HasAppPermission.
    Usage: @has_app_permission('user', 'create')
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            # Create permission instance
            permission = HasAppPermission(app_label, action)
            
            try:
                # Decorator may run before DRF Request/authentication initialization.
                # If request.user is still anonymous, try JWT auth from Authorization header.
                user = getattr(request, "user", None)
                if not getattr(user, "is_authenticated", False):
                    try:
                        auth_result = JWTAuthentication().authenticate(request)
                        if auth_result:
                            request.user = auth_result[0]
                    except Exception:
                        # Keep anonymous user; permission layer will return proper 401.
                        pass

                # Check permission
                if not permission.has_permission(request, None):
                    # This line should never be reached as has_permission raises exception on failure
                    raise PermissionDenied("Unknown permission error")
            except PermissionDenied as e:
                detail = getattr(e, "detail", "Permission denied")
                code = getattr(e, "get_codes", lambda: "permission_denied")()
                if isinstance(code, dict):
                    code = next(iter(code.values()), "permission_denied")

                # Since this decorator runs outside DRF's exception handler for function-based views,
                # convert permission exceptions to explicit API responses.
                response_status = 401 if code == "not_authenticated" else 403
                return JsonResponse(
                    {"detail": str(detail), "code": code},
                    status=response_status
                )
            
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator
