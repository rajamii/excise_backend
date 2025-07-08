from functools import wraps
from rest_framework.exceptions import PermissionDenied
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
                # Check permission
                if not permission.has_permission(request, None):
                    # This line should never be reached as has_permission raises exception on failure
                    raise PermissionDenied("Unknown permission error")
            except PermissionDenied as e:
                # Re-raise the exception to be handled by DRF
                raise e
            
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator
