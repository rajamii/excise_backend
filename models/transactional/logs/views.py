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
    month = request.query_params.get('month')          # format: YYYY-MM
    action = request.query_params.get('action')        # LOGIN or LOGOUT
    date = request.query_params.get('date')            # format: YYYY-MM-DD
    page_raw = request.query_params.get('page')
    page_size_raw = request.query_params.get('page_size')
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

    # Filter by action (LOGIN / LOGOUT) — takes precedence over generic activity_type
    if action:
        queryset = queryset.filter(activity_type=action.upper())

    # Filter by month (YYYY-MM)
    if month and not date:  # skip month if a specific date is provided
        try:
            year, mon = month.split('-')
            queryset = queryset.filter(timestamp__year=int(year), timestamp__month=int(mon))
        except (ValueError, AttributeError):
            pass  # ignore malformed month param

    # Filter by specific date (YYYY-MM-DD) — overrides month filter
    if date:
        try:
            from datetime import datetime
            parsed = datetime.strptime(date, '%Y-%m-%d').date()
            queryset = queryset.filter(timestamp__date=parsed)
        except (ValueError, AttributeError):
            pass  # ignore malformed date param

    queryset = queryset.order_by('-timestamp')

    # Pagination support
    try:
        page = int(page_raw) if page_raw is not None else None
        page_size = int(page_size_raw) if page_size_raw is not None else None
    except (ValueError, TypeError):
        page = None
        page_size = None

    if page is not None and page_size is not None:
        page = max(1, page)
        page_size = max(1, min(page_size, 200))
        total_count = queryset.count()
        offset = (page - 1) * page_size
        items = queryset[offset: offset + page_size]
        serializer = UserActivitySerializer(items, many=True)
        return Response({
            'count': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': (total_count + page_size - 1) // page_size,
            'results': serializer.data,
        })

    # Legacy limit-based response (backwards compatible)
    try:
        limit = int(limit_raw) if limit_raw is not None else 100
    except Exception:
        limit = 100
    limit = max(1, min(limit, 500))
    
    serializer = UserActivitySerializer(queryset[:limit], many=True)
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([HasAppPermission('logs', 'create')])
def track_custom_activity(request):
    serializer = UserActivitySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)
