from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from auth.roles.decorators import has_app_permission

from .models import CompanyModel
from .serializers import CompanySerializer

#################################################
#           Company Registration                #
#################################################

@has_app_permission('company_registration', 'view')
@api_view(['GET'])
def company_list(request):
    """List active company registrations with filters"""
    queryset = CompanyModel.objects.filter(IsActive=True)
    
    # Optional filters
    application_year = request.query_params.get('application_year')
    company_name = request.query_params.get('company_name')
    pan = request.query_params.get('pan')
    brand_type = request.query_params.get('brand_type')
    
    if application_year:
        queryset = queryset.filter(applicationYear=application_year)
    if company_name:
        queryset = queryset.filter(companyName__icontains=company_name)
    if pan:
        queryset = queryset.filter(pan=pan)
    if brand_type:
        queryset = queryset.filter(brandType=brand_type)
    
    serializer = CompanySerializer(queryset, many=True)
    return Response({
        'count': queryset.count(),
        'results': serializer.data
    })

@has_app_permission('company_registration', 'create')
@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
def company_create(request):
    """Create new company registration"""
    serializer = CompanySerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@has_app_permission('company_registration', 'view')
@api_view(['GET'])
def company_detail(request, pk):
    """Retrieve active company registration by PK"""
    company = get_object_or_404(CompanyModel, pk=pk, IsActive=True)
    serializer = CompanySerializer(company)
    return Response(serializer.data)

@has_app_permission('company_registration', 'view')
@api_view(['GET'])
def company_detail_by_appid(request, application_id):
    """Retrieve active company registration by application ID"""
    company = get_object_or_404(
        CompanyModel, 
        applicationId=application_id, 
        IsActive=True
    )
    serializer = CompanySerializer(company)
    return Response(serializer.data)

@has_app_permission('company_registration', 'update')
@api_view(['PUT', 'PATCH'])
@parser_classes([MultiPartParser, FormParser])
def company_update(request, pk):
    """Update company registration by PK"""
    company = get_object_or_404(CompanyModel, pk=pk)
    serializer = CompanySerializer(
        instance=company,
        data=request.data,
        partial=request.method == 'PATCH'
    )
    
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@has_app_permission('company_registration', 'update')
@api_view(['PUT', 'PATCH'])
@parser_classes([MultiPartParser, FormParser])
def company_update_by_appid(request, application_id):
    """Update company registration by application ID"""
    company = get_object_or_404(
        CompanyModel, 
        applicationId=application_id
    )
    serializer = CompanySerializer(
        instance=company,
        data=request.data,
        partial=request.method == 'PATCH'
    )
    
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@has_app_permission('company_registration', 'delete')
@api_view(['DELETE'])
def company_delete(request, pk):
    """Soft delete company registration by PK"""
    company = get_object_or_404(CompanyModel, pk=pk)
    company.IsActive = False
    company.save()
    return Response(
        {'message': f'Company {company.companyName} deactivated'},
        status=status.HTTP_200_OK
    )

@has_app_permission('company_registration', 'delete')
@api_view(['DELETE'])
def company_delete_by_appid(request, application_id):
    """Soft delete company registration by application ID"""
    company = get_object_or_404(
        CompanyModel, 
        applicationId=application_id
    )
    company.IsActive = False
    company.save()
    return Response(
        {'message': f'Company {company.companyName} deactivated'},
        status=status.HTTP_200_OK
    )
