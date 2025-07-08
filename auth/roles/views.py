from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied

from .models import Role
from .serializers import RoleSerializer
from .permissions import HasAppPermission
from .decorators import has_app_permission

def get_user_role(user):
    """Helper to get user's role instance"""
    return getattr(user, 'role', None)

#################################################
#                  Role Views                   #
#################################################

@has_app_permission('roles', 'view')
@api_view(['GET'])
def role_list(request):
    """List all roles"""
    roles = Role.objects.all()
    serializer = RoleSerializer(roles, many=True)
    return Response(serializer.data)

@has_app_permission('roles', 'create')
@api_view(['POST'])
def role_create(request):
    """Create a new role"""
    serializer = RoleSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@has_app_permission('roles', 'view')
@api_view(['GET'])
def role_detail(request, role_id):
    """Retrieve a specific role"""
    try:
        role = Role.objects.get(role_id=role_id)
    except Role.DoesNotExist:
        return Response(
            {"detail": "Role not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    serializer = RoleSerializer(role)
    return Response(serializer.data)

@has_app_permission('roles', 'update')
@api_view(['PUT', 'PATCH'])
def role_update(request, role_id):
    """Update a role"""
    try:
        role = Role.objects.get(role_id=role_id)
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

@has_app_permission('roles', 'delete')
@api_view(['DELETE'])
def role_delete(request, role_id):
    """Delete a role"""
    try:
        role = Role.objects.get(role_id=role_id)
    except Role.DoesNotExist:
        return Response(
            {"detail": "Role not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    role.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)
