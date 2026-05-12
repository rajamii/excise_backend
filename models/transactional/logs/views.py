 # views/user_activity_views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from auth.roles.permissions import HasAppPermission
from .models import UserActivity
from .serializer import UserActivitySerializer

User = get_user_model()

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_activity_list(request):
    user_id = request.query_params.get('user_id')
    activity_type = request.query_params.get('type')
    limit_raw = request.query_params.get('limit')

    def _has_logs_view_permission() -> bool:
        try:
            return HasAppPermission('logs', 'view').has_permission(request, None)
        except PermissionDenied:
            return False
        except Exception:
            return False
    
    queryset = UserActivity.objects.all()
    if not _has_logs_view_permission():
        # Non-admin users can only view their own activity (including actions performed on them).
        queryset = queryset.filter(Q(user=request.user) | Q(target_user=request.user))
    
    if user_id:
        if _has_logs_view_permission():
            queryset = queryset.filter(user__id=user_id)
    if activity_type:
        queryset = queryset.filter(activity_type=activity_type)

    try:
        limit = int(limit_raw) if limit_raw is not None else 100
    except Exception:
        limit = 100
    limit = max(1, min(limit, 500))
    
    serializer = UserActivitySerializer(
        queryset.order_by('-timestamp')[:limit],
        many=True
    )
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([HasAppPermission('logs', 'create')])
def track_custom_activity(request):
    serializer = UserActivitySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)
