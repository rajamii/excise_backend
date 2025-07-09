 # views.py

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from auth.roles.decorators import has_app_permission

# Local app imports
from . import models as masters_model
from .serializers.licensecategory_serializer import LicenseCategorySerializer
from .serializers.licensetype_serializer import LicenseTypeSerializer
from .serializers.state_serializer import StateSerializer
from .serializers.district_serilizer import DistrictSerializer
from .serializers.subdivision_serializer import SubdivisionSerializer
from .serializers.policestation_serializer import PoliceStationSerializer

#################################################
#           License Category                    #
#################################################

@has_app_permission('core', 'view')
@api_view(['GET'])
def license_category_list(request):
    """List all license categories."""
    queryset = masters_model.LicenseCategory.objects.all()
    serializer = LicenseCategorySerializer(queryset, many=True)
    return Response({
        'count': queryset.count(),
        'results': serializer.data
    })

@has_app_permission('core', 'create')
@api_view(['POST'])
def license_category_create(request):
    """Create a new license category."""
    serializer = LicenseCategorySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)

@has_app_permission('core', 'view')
@api_view(['GET'])
def license_category_detail(request, pk):
    """Retrieve a license category instance."""
    category = get_object_or_404(masters_model.LicenseCategory, pk=pk)
    serializer = LicenseCategorySerializer(category)
    return Response(serializer.data)

@has_app_permission('core', 'update')
@api_view(['PUT', 'PATCH'])
def license_category_update(request, pk):
    """Update a license category instance."""
    category = get_object_or_404(masters_model.LicenseCategory, pk=pk)
    serializer = LicenseCategorySerializer(category, data=request.data, partial=request.method == 'PATCH')
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)

@has_app_permission('core', 'delete')
@api_view(['DELETE'])
def license_category_delete(request, pk):
    """Delete a license category instance."""
    category = get_object_or_404(masters_model.LicenseCategory, pk=pk)
    category.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


#################################################
#           License Type                        #
#################################################

@has_app_permission('core', 'view')
@api_view(['GET'])
def license_type_list(request):
    """List all license types."""
    queryset = masters_model.LicenseType.objects.all()
    serializer = LicenseTypeSerializer(queryset, many=True)
    return Response({
        'count': queryset.count(),
        'results': serializer.data
    })

@has_app_permission('core', 'create')
@api_view(['POST'])
def license_type_create(request):
    """Create a new license type."""
    serializer = LicenseTypeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)

@has_app_permission('core', 'view')
@api_view(['GET'])
def license_type_detail(request, pk):
    """Retrieve a license type instance."""
    license_type = get_object_or_404(masters_model.LicenseType, pk=pk)
    serializer = LicenseTypeSerializer(license_type)
    return Response(serializer.data)

@has_app_permission('core', 'update')
@api_view(['PUT', 'PATCH'])
def license_type_update(request, pk):
    """Update a license type instance."""
    license_type = get_object_or_404(masters_model.LicenseType, pk=pk)
    serializer = LicenseTypeSerializer(license_type, data=request.data, partial=request.method == 'PATCH')
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)

@has_app_permission('core', 'delete')
@api_view(['DELETE'])
def license_type_delete(request, pk):
    """Delete a license type instance."""
    license_type = get_object_or_404(masters_model.LicenseType, pk=pk)
    license_type.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


#################################################
#           State                               #
#################################################

@has_app_permission('core', 'view')
@api_view(['GET'])
def state_list(request):
    """List all active states."""
    queryset = masters_model.State.objects.filter(IsActive=True)
    serializer = StateSerializer(queryset, many=True, context={'request': request})
    return Response({
        'count': queryset.count(),
        'results': serializer.data
    })

@has_app_permission('core', 'create')
@api_view(['POST'])
def state_create(request):
    """Create a new state."""
    serializer = StateSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)

@has_app_permission('core', 'view')
@api_view(['GET'])
def state_detail(request, state_code):
    """Retrieve an active state instance."""
    state = get_object_or_404(masters_model.State, StateCode=state_code, IsActive=True)
    serializer = StateSerializer(state, context={'request': request})
    return Response(serializer.data)

@has_app_permission('core', 'update')
@api_view(['PUT', 'PATCH'])
def state_update(request, state_code):
    """Update a state instance."""
    state = get_object_or_404(masters_model.State, StateCode=state_code)
    serializer = StateSerializer(instance=state, data=request.data, partial=request.method == 'PATCH', context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)

@has_app_permission('core', 'delete')
@api_view(['DELETE'])
def state_delete(request, state_code):
    """Deactivate a state instance (soft delete)."""
    state = get_object_or_404(masters_model.State, StateCode=state_code)
    state.IsActive = False
    state.save()
    return Response(
        {'message': f'State {state.State} deactivated successfully.'},
        status=status.HTTP_200_OK
    )


#################################################
#           District                            #
#################################################

@has_app_permission('masters', 'view')
@api_view(['GET'])
def district_list(request):
    """List all active districts, optionally filtered by state_code."""
    queryset = masters_model.District.objects.filter(IsActive=True)
    state_code = request.query_params.get('state_code')
    if state_code:
        queryset = queryset.filter(StateCode=state_code)
    
    serializer = DistrictSerializer(queryset, many=True, context={'request': request})
    return Response({
        'count': queryset.count(),
        'results': serializer.data
    })

@has_app_permission('masters', 'create')
@api_view(['POST'])
def district_create(request):
    """Create a new district."""
    serializer = DistrictSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)

@has_app_permission('masters', 'view')
@api_view(['GET'])
def district_detail(request, district_code):
    """Retrieve an active district instance."""
    district = get_object_or_404(masters_model.District, DistrictCode=district_code, IsActive=True)
    serializer = DistrictSerializer(district, context={'request': request})
    return Response(serializer.data)

@has_app_permission('masters', 'update')
@api_view(['PUT', 'PATCH'])
def district_update(request, district_code):
    """Update a district instance."""
    district = get_object_or_404(masters_model.District, DistrictCode=district_code)
    serializer = DistrictSerializer(instance=district, data=request.data, partial=request.method == 'PATCH', context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)

@has_app_permission('masters', 'delete')
@api_view(['DELETE'])
def district_delete(request, district_code):
    """Deactivate a district instance (soft delete)."""
    district = get_object_or_404(masters_model.District, DistrictCode=district_code)
    if district.subdivisions.filter(IsActive=True).exists():
        return Response(
            {"error": "Cannot deactivate district with active subdivisions."},
            status=status.HTTP_400_BAD_REQUEST
        )
    district.IsActive = False
    district.save()
    return Response(
        {'message': f'District {district.District} deactivated successfully.'},
        status=status.HTTP_200_OK
    )


#################################################
#           Subdivision                         #
#################################################

@has_app_permission('masters', 'view')
@api_view(['GET'])
def subdivision_list(request):
    """List all active subdivisions, optionally filtered by district_code."""
    queryset = masters_model.Subdivision.objects.filter(IsActive=True)
    district_code = request.query_params.get('district_code')
    if district_code:
        queryset = queryset.filter(DistrictCode=district_code)

    serializer = SubdivisionSerializer(queryset, many=True, context={'request': request})
    return Response({
        'count': queryset.count(),
        'results': serializer.data
    })

@has_app_permission('masters', 'create')
@api_view(['POST'])
def subdivision_create(request):
    """Create a new subdivision."""
    serializer = SubdivisionSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)

@has_app_permission('masters', 'view')
@api_view(['GET'])
def subdivision_detail(request, subdivision_code):
    """Retrieve an active subdivision instance."""
    subdivision = get_object_or_404(masters_model.Subdivision, SubDivisionCode=subdivision_code, IsActive=True)
    serializer = SubdivisionSerializer(subdivision, context={'request': request})
    return Response(serializer.data)

@has_app_permission('masters', 'update')
@api_view(['PUT', 'PATCH'])
def subdivision_update(request, subdivision_code):
    """Update a subdivision instance."""
    subdivision = get_object_or_404(masters_model.Subdivision, SubDivisionCode=subdivision_code)
    serializer = SubdivisionSerializer(instance=subdivision, data=request.data, partial=request.method == 'PATCH', context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)

@has_app_permission('masters', 'delete')
@api_view(['DELETE'])
def subdivision_delete(request, subdivision_code):
    """Deactivate a subdivision instance (soft delete)."""
    subdivision = get_object_or_404(masters_model.Subdivision, SubDivisionCode=subdivision_code)
    if subdivision.police_stations.filter(IsActive=True).exists():
        return Response(
            {"error": "Cannot deactivate subdivision with active police stations."},
            status=status.HTTP_400_BAD_REQUEST
        )
    subdivision.IsActive = False
    subdivision.save()
    return Response(
        {'message': f'Subdivision {subdivision.SubDivisionName} deactivated successfully.'},
        status=status.HTTP_200_OK
    )


#################################################
#           Police Station                      #
#################################################

@has_app_permission('masters', 'view')
@api_view(['GET'])
def policestation_list(request):
    """List active police stations, optionally filtered by subdivision_code."""
    queryset = masters_model.PoliceStation.objects.filter(IsActive=True)
    subdivision_code = request.query_params.get('subdivision_code')
    if subdivision_code:
        queryset = queryset.filter(SubDivisionCode=subdivision_code)

    serializer = PoliceStationSerializer(queryset, many=True, context={'request': request})
    return Response({
        'count': queryset.count(),
        'results': serializer.data
    })

@has_app_permission('masters', 'create')
@api_view(['POST'])
def policestation_create(request):
    """Create a new police station."""
    serializer = PoliceStationSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)

@has_app_permission('masters', 'view')
@api_view(['GET'])
def policestation_detail(request, policestation_code):
    """Retrieve an active police station instance."""
    station = get_object_or_404(masters_model.PoliceStation, PoliceStationCode=policestation_code, IsActive=True)
    serializer = PoliceStationSerializer(station, context={'request': request})
    return Response(serializer.data)

@has_app_permission('masters', 'update')
@api_view(['PUT', 'PATCH'])
def policestation_update(request, policestation_code):
    """Update a police station instance."""
    station = get_object_or_404(masters_model.PoliceStation, PoliceStationCode=policestation_code)
    serializer = PoliceStationSerializer(instance=station, data=request.data, partial=request.method == 'PATCH', context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)

@has_app_permission('masters', 'delete')
@api_view(['DELETE'])
def policestation_delete(request, policestation_code):
    """Deactivate a police station instance (soft delete)."""
    station = get_object_or_404(masters_model.PoliceStation, PoliceStationCode=policestation_code)
    station.IsActive = False
    station.save()
    return Response(
        {'message': f'Police Station {station.PoliceStationName} deactivated successfully.'},
        status=status.HTTP_200_OK
    )
