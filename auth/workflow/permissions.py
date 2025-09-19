from rest_framework import permissions
from .models import StagePermission
from models.transactional.license_application.models import LicenseApplication

class HasStagePermission(permissions.BasePermission):
    """Checks if a user's role has permission to process a stage."""

    def has_permission(self, request, view):
        # For advance views, infer current stage from application_id in kwargs
        application_id = view.kwargs.get("application_id")
        if application_id:
            try:
                application = LicenseApplication.objects.get(application_id=application_id)
                stage_id = application.current_stage_id
            except LicenseApplication.DoesNotExist:
                return False
        else:        
            # Try to get stage_id from URL kwargs, request.data, or query params
            stage_id = (
                view.kwargs.get("stage_id") or
                request.data.get("stage_id") or
                request.query_params.get("stage_id")
            )

        # If no stage_id provided (e.g., list views), allow access (read-only)
        if not stage_id:
            return True

        # Check if user's role can process this stage
        try:
            return StagePermission.objects.filter(
                stage_id=stage_id,
                role=request.user.role,
                can_process=True
            ).exists()
        except AttributeError:
            return False  # User has no role assigned
