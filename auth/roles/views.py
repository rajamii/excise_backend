from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied

from .models import Role, DashboardRoleConfig
from .serializers import RoleSerializer, DashboardRoleConfigSerializer
from .permissions import HasAppPermission
from .decorators import has_app_permission

def get_user_role(user):
    """Helper to get user's role instance"""
    return getattr(user, 'role', None)

#################################################
#                  Role Views                   #
#################################################

@permission_classes([HasAppPermission('roles', 'view')])
@api_view(['GET'])
def role_list(request):
    """List all roles"""
    roles = Role.objects.all().order_by('id')
    serializer = RoleSerializer(roles, many=True)
    return Response(serializer.data)

@permission_classes([HasAppPermission('roles', 'create')])
@api_view(['POST'])
def role_create(request):
    """Create a new role"""
    serializer = RoleSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@permission_classes([HasAppPermission('roles', 'view')])
@api_view(['GET'])
def role_detail(request, pk):
    """Retrieve a specific role"""
    try:
        role = Role.objects.get(pk=pk)
    except Role.DoesNotExist:
        return Response(
            {"detail": "Role not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    serializer = RoleSerializer(role)
    return Response(serializer.data)

@permission_classes([HasAppPermission('roles', 'update')])
@api_view(['PUT', 'PATCH'])
def role_update(request, pk):
    """Update a role"""
    try:
        role = Role.objects.get(pk=pk)
    except Role.DoesNotExist:
        return Response(
            {"detail": "Role not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    serializer = RoleSerializer(role, data=request.data, partial=request.method == 'PATCH')
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@permission_classes([HasAppPermission('roles', 'delete')])
@api_view(['DELETE'])
def role_delete(request, pk):
    """Delete a role"""
    try:
        role = Role.objects.get(pk=pk)
    except Role.DoesNotExist:
        return Response(
            {"detail": "Role not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    role.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@permission_classes([IsAuthenticated])
@api_view(['GET'])
def current_dashboard_config(request):
    user_role = get_user_role(request.user)
    if not user_role:
        return Response({"detail": "User role not found"}, status=status.HTTP_404_NOT_FOUND)

    config = DashboardRoleConfig.objects.filter(role=user_role, is_active=True).first()
    if not config:
        return Response({"detail": "Dashboard config not found"}, status=status.HTTP_404_NOT_FOUND)

    serializer = DashboardRoleConfigSerializer(config)
    return Response(serializer.data)


@permission_classes([HasAppPermission('roles', 'view')])
@api_view(['GET'])
def dashboard_config_by_role(request, role_id):
    config = DashboardRoleConfig.objects.filter(role_id=role_id, is_active=True).first()
    if not config:
        return Response({"detail": "Dashboard config not found"}, status=status.HTTP_404_NOT_FOUND)

    serializer = DashboardRoleConfigSerializer(config)
    return Response(serializer.data)
