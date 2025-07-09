from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from auth.roles.decorators import has_app_permission

from .models import SalesmanBarmanModel
from .serializers import SalesmanBarmanSerializer

#################################################
#           Salesman/Barman                     #
#################################################

@has_app_permission('masters', 'view')
@api_view(['GET'])
def salesman_barman_list(request):
    """List active salesman/barman records with filters"""
    queryset = SalesmanBarmanModel.objects.filter(IsActive=True)
    
    # Optional filters
    role = request.query_params.get('role')
    district = request.query_params.get('district')
    license_category = request.query_params.get('license_category')
    application_id = request.query_params.get('application_id')
    
    if role:
        queryset = queryset.filter(role=role)
    if district:
        queryset = queryset.filter(district__icontains=district)
    if license_category:
        queryset = queryset.filter(licenseCategory__icontains=license_category)
    if application_id:
        queryset = queryset.filter(applicationId=application_id)
    
    serializer = SalesmanBarmanSerializer(queryset, many=True)
    return Response({
        'count': queryset.count(),
        'results': serializer.data
    })

@has_app_permission('masters', 'create')
@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
def salesman_barman_create(request):
    """Create new salesman/barman record"""
    serializer = SalesmanBarmanSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@has_app_permission('masters', 'view')
@api_view(['GET'])
def salesman_barman_detail(request, pk):
    """Retrieve active salesman/barman record by PK"""
    record = get_object_or_404(SalesmanBarmanModel, pk=pk, IsActive=True)
    serializer = SalesmanBarmanSerializer(record)
    return Response(serializer.data)

@has_app_permission('masters', 'view')
@api_view(['GET'])
def salesman_barman_detail_by_appid(request, application_id):
    """Retrieve active salesman/barman record by application ID"""
    record = get_object_or_404(
        SalesmanBarmanModel, 
        applicationId=application_id, 
        IsActive=True
    )
    serializer = SalesmanBarmanSerializer(record)
    return Response(serializer.data)

@has_app_permission('masters', 'update')
@api_view(['PUT', 'PATCH'])
@parser_classes([MultiPartParser, FormParser])
def salesman_barman_update(request, pk):
    """Update salesman/barman record by PK"""
    record = get_object_or_404(SalesmanBarmanModel, pk=pk)
    serializer = SalesmanBarmanSerializer(
        instance=record,
        data=request.data,
        partial=request.method == 'PATCH'
    )
    
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@has_app_permission('masters', 'update')
@api_view(['PUT', 'PATCH'])
@parser_classes([MultiPartParser, FormParser])
def salesman_barman_update_by_appid(request, application_id):
    """Update salesman/barman record by application ID"""
    record = get_object_or_404(
        SalesmanBarmanModel, 
        applicationId=application_id
    )
    serializer = SalesmanBarmanSerializer(
        instance=record,
        data=request.data,
        partial=request.method == 'PATCH'
    )
    
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@has_app_permission('masters', 'delete')
@api_view(['DELETE'])
def salesman_barman_delete(request, pk):
    """Soft delete salesman/barman record by PK"""
    record = get_object_or_404(SalesmanBarmanModel, pk=pk)
    record.IsActive = False
    record.save()
    return Response(
        {'message': f'{record.role} {record.firstName} {record.lastName} deactivated'},
        status=status.HTTP_200_OK
    )

@has_app_permission('masters', 'delete')
@api_view(['DELETE'])
def salesman_barman_delete_by_appid(request, application_id):
    """Soft delete salesman/barman record by application ID"""
    record = get_object_or_404(
        SalesmanBarmanModel, 
        applicationId=application_id
    )
    record.IsActive = False
    record.save()
    return Response(
        {'message': f'{record.role} {record.firstName} {record.lastName} deactivated'},
        status=status.HTTP_200_OK
    )
