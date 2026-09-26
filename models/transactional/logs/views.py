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


# ═════════════════════════════════════════════════════════════════════════════
# ADMIN AUDIT LOG VIEWS ('admin_log' table)
# ═════════════════════════════════════════════════════════════════════════════
from .models import AdminLog
from .serializer import AdminLogSerializer
from .services import log_admin_action

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_log_list(request):
    """
    List and filter all administrative audit logs across all modules.
    Supports filtering by module, application ID, action, username, role, date, month, and date ranges.
    """
    def _is_admin_user(user) -> bool:
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or user.is_staff:
            return True
        role_id = getattr(user, 'role_id', None) or (user.role.id if getattr(user, 'role', None) else None)
        if role_id in [1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]:
            return True
        role_name = str(getattr(user, 'role', '') or '').lower()
        if any(kw in role_name for kw in ['admin', 'commissioner', 'officer', 'cell', 'window', 'district', 'secretary', 'enquiry', 'inquiry']):
            return True
        try:
            return HasAppPermission('logs', 'view').has_permission(request, None)
        except Exception:
            return False

    is_admin = _is_admin_user(request.user)
    scope = str(request.query_params.get('scope') or 'mine').strip().lower()

    queryset = AdminLog.objects.all()

    if not is_admin:
        # Non-admin / Licensee users can ONLY view actions performed BY THEM (their own activity).
        # Actions performed by Site Admin or excise officers (e.g. security amount deductions, administrative updates) are kept with Site Admin/officers only.
        queryset = queryset.filter(
            Q(user=request.user) |
            Q(username__iexact=request.user.username) |
            Q(admin_id=str(request.user.pk))
        ).exclude(
            Q(role__iexact="Site Admin") |
            Q(username__iexact="admin") |
            Q(username__iexact="SYSTEM")
        )
    else:
        # By default, officers/admins view their own action audit records (scope='mine')
        # If scope='all' or role/username/admin_id is explicitly requested, broader logs are shown
        if scope != 'all' and not request.query_params.get('username') and not request.query_params.get('role') and not request.query_params.get('admin_id'):
            queryset = queryset.filter(
                Q(username=request.user.username) |
                Q(admin_id=str(request.user.pk)) |
                Q(user=request.user)
            )

    # Filters
    module_name = request.query_params.get('module_name') or request.query_params.get('module')
    application_id = request.query_params.get('application_id') or request.query_params.get('app_id')
    action = request.query_params.get('action')
    username = request.query_params.get('username')
    role = request.query_params.get('role')
    admin_id = request.query_params.get('admin_id') or request.query_params.get('user_id')
    search = request.query_params.get('search')

    # Date filters
    date = request.query_params.get('date')            # format: YYYY-MM-DD
    from_date = request.query_params.get('from_date') or request.query_params.get('start_date')  # YYYY-MM-DD
    to_date = request.query_params.get('to_date') or request.query_params.get('end_date')        # YYYY-MM-DD
    month = request.query_params.get('month')          # format: YYYY-MM

    page_raw = request.query_params.get('page')
    page_size_raw = request.query_params.get('page_size')
    limit_raw = request.query_params.get('limit')

    if module_name:
        queryset = queryset.filter(module_name__icontains=module_name.strip())

    if application_id:
        queryset = queryset.filter(application_id__icontains=application_id.strip())

    if action:
        queryset = queryset.filter(action__iexact=action.strip())

    if username:
        queryset = queryset.filter(username__icontains=username.strip())

    if role:
        queryset = queryset.filter(role__icontains=role.strip())

    if admin_id:
        queryset = queryset.filter(admin_id=str(admin_id).strip())

    if search:
        s = search.strip()
        queryset = queryset.filter(
            Q(username__icontains=s) |
            Q(full_name__icontains=s) |
            Q(role__icontains=s) |
            Q(module_name__icontains=s) |
            Q(application_id__icontains=s) |
            Q(action__icontains=s) |
            Q(remarks__icontains=s) |
            Q(from_stage__icontains=s) |
            Q(to_stage__icontains=s) |
            Q(to_stage_name__icontains=s) |
            Q(to_stage_username__icontains=s)
        )

    # Date range logic
    if date:
        try:
            from datetime import datetime
            parsed = datetime.strptime(date.strip(), '%Y-%m-%d').date()
            queryset = queryset.filter(timestamp__date=parsed)
        except Exception:
            pass
    elif from_date or to_date:
        from datetime import datetime
        if from_date:
            try:
                parsed_from = datetime.strptime(from_date.strip(), '%Y-%m-%d').date()
                queryset = queryset.filter(timestamp__date__gte=parsed_from)
            except Exception:
                pass
        if to_date:
            try:
                parsed_to = datetime.strptime(to_date.strip(), '%Y-%m-%d').date()
                queryset = queryset.filter(timestamp__date__lte=parsed_to)
            except Exception:
                pass
    elif month:
        try:
            year, mon = month.strip().split('-')
            queryset = queryset.filter(timestamp__year=int(year), timestamp__month=int(mon))
        except Exception:
            pass

    queryset = queryset.order_by('-timestamp')

    # Pagination
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
        serializer = AdminLogSerializer(items, many=True)
        return Response({
            'count': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': (total_count + page_size - 1) // page_size,
            'results': serializer.data,
        })

    # Limit fallback
    try:
        limit = int(limit_raw) if limit_raw is not None else 100
    except Exception:
        limit = 100
    limit = max(1, min(limit, 500))

    serializer = AdminLogSerializer(queryset[:limit], many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_log_history(request, application_id):
    """
    Returns the complete chronological history of actions for a given application/reference ID.
    """
    app_id_clean = str(application_id).strip()
    logs = AdminLog.objects.filter(
        Q(application_id=app_id_clean) |
        Q(application_id__iexact=app_id_clean) |
        Q(object_id=app_id_clean)
    ).order_by('timestamp')

    serializer = AdminLogSerializer(logs, many=True)
    return Response({
        'application_id': application_id,
        'count': logs.count(),
        'history': serializer.data
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_log_modules(request):
    """
    Returns distinct module names recorded in the audit log.
    """
    modules = AdminLog.objects.values_list('module_name', flat=True).distinct().order_by('module_name')
    return Response(list(modules))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_log_actions(request):
    """
    Returns distinct action types recorded in the audit log.
    """
    actions = AdminLog.objects.exclude(action__isnull=True).exclude(action__exact='').values_list('action', flat=True).distinct().order_by('action')
    return Response(list(actions))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_log_roles(request):
    """
    Returns distinct roles recorded in the audit log.
    """
    roles = AdminLog.objects.exclude(role__isnull=True).exclude(role__exact='').values_list('role', flat=True).distinct().order_by('role')
    return Response(list(roles))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def track_admin_log(request):
    """
    Endpoint allowing administrative frontends/services to explicitly log custom admin actions.
    """
    action = request.data.get('action')
    if not action:
        return Response({'detail': 'action is required'}, status=status.HTTP_400_BAD_REQUEST)

    entry = log_admin_action(
        action=action,
        user=request.user,
        request=request,
        module_name=request.data.get('module_name') or request.data.get('module'),
        application_id=request.data.get('application_id') or request.data.get('app_id'),
        from_stage=request.data.get('from_stage'),
        to_stage=request.data.get('to_stage'),
        status=request.data.get('status'),
        remarks=request.data.get('remarks'),
        reverted_by=request.data.get('reverted_by'),
        reverted_to=request.data.get('reverted_to'),
        reverted_to_stage=request.data.get('reverted_to_stage'),
        metadata=request.data.get('metadata')
    )

    if not entry:
        return Response({'detail': 'Failed to record admin log'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    serializer = AdminLogSerializer(entry)
    return Response(serializer.data, status=status.HTTP_201_CREATED)

