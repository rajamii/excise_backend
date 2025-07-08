from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied
from typing import Literal, NoReturn

PermissionAction = Literal['view', 'create', 'update', 'delete']

class HasAppPermission(permissions.BasePermission):
    """
    Strictly typed permission checker that raises PermissionDenied.
    Usage: @permission_classes([HasAppPermission('blog', 'create')])
    """

    def __init__(self, app_label: str, action: PermissionAction):
        self.app_label = app_label
        self.action = action
        self._permission_fields = {
            'view': 'can_view',
            'create': 'can_add',
            'update': 'can_update',
            'delete': 'can_delete'
        }

    def _raise_denied(self, detail: str, code: str) -> NoReturn:

        """Helper to consistently raise PermissionDenied"""
        raise PermissionDenied(detail=detail, code=code)

    def has_permission(self, request, view) -> bool:  # type: ignore[override]
        # Authentication check
        if not request.user.is_authenticated:
            self._raise_denied(
                "Authentication required",
                "not_authenticated"
            )

        # Superuser bypass
        if getattr(request.user, 'is_superuser', False):
            return True

        # Role check
        role = getattr(request.user, 'role', None)
        if not role:
            self._raise_denied(
                "No role assigned",
                "no_role"
            )

        # Action validation
        permission_field = self._permission_fields.get(self.action)
        if not permission_field:
            self._raise_denied(
                f"Invalid action: {self.action}",
                "invalid_action"
            )

        # Permission check
        if self.app_label not in getattr(role, permission_field, []):
            self._raise_denied(
                f"Cannot {self.action} {self.app_label}",
                f"cannot_{self.action}"
            )

        return True  # Explicit return for type checker
