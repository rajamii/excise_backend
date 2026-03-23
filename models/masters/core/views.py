from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from auth.roles.permissions import HasAppPermission  # type: ignore

from . import models as masters_model
from .serializers.licensecategory_serializer import LicenseCategorySerializer
from .serializers.licensetype_serializer import LicenseTypeSerializer
from .serializers.state_serializer import StateSerializer
from .serializers.district_serializer import DistrictSerializer
from .serializers.subdivision_serializer import SubdivisionSerializer
from .serializers.policestation_serializer import PoliceStationSerializer
from .serializers.licensesubcategory_serializer import LicenseSubcategorySerializer
from .serializers.licensetitle_serializer import LicenseTitleSerializer
from .serializers.road_serializer import RoadSerializer
from .serializers.location_serializer import LocationSerializer
from .serializers.licensefee_serializer import LicenseFeeSerializer
from .serializers.locationcategory_serializer import LocationCategorySerializer
from .serializers.locationsubcategory_serializer import LocationSubcategorySerializer
from .serializers.ward_serializer import WardSerializer

# NOTE: LicenseeProfile views have been moved to auth.user.views.
# Endpoints are now served under /api/users/licensee-profiles/


@permission_classes([AllowAny])
@authentication_classes([])
@api_view(['GET'])
def timer_config(request):
    """
    Read timer config from public.timer (SupplyChainTimerConfig) by code.

    Example:
      GET /masters/core/timer-config/?code=INACTIVITY_LOGOUT
    """
    code = str(request.query_params.get('code') or '').strip()
    if not code:
        return Response({'error': 'code is required'}, status=status.HTTP_400_BAD_REQUEST)

    # Backend fallback only; frontend should rely on DB config.
    # Defaults vary by timer code.
    default_seconds_by_code = {
        'INACTIVITY_LOGOUT': 4 * 60,
        'INACTIVITY_WARNING': 30,
    }
    default_seconds = int(default_seconds_by_code.get(code, 4 * 60))

    cfg = (
        masters_model.SupplyChainTimerConfig.objects.filter(code=code, is_active=True)
        .order_by('-updated_at', '-id')
        .first()
    )
    if not cfg:
        return Response(
            {
                'code': code,
                'is_active': False,
                'delay_seconds': default_seconds,
                'delay_ms': default_seconds * 1000,
                'source': 'default',
            },
            status=status.HTTP_200_OK,
        )

    unit = str(getattr(cfg, 'delay_unit', '') or '').lower().strip()
    value = int(getattr(cfg, 'delay_value', 0) or 0)
    if value < 0:
        value = 0

    multiplier = 1
    if unit == masters_model.SupplyChainTimerConfig.TIMER_UNIT_MINUTE:
        multiplier = 60
    elif unit == masters_model.SupplyChainTimerConfig.TIMER_UNIT_HOUR:
        multiplier = 60 * 60
    elif unit == masters_model.SupplyChainTimerConfig.TIMER_UNIT_DAY:
        multiplier = 24 * 60 * 60

    seconds = max(0, value * multiplier)
    return Response(
        {
            'code': cfg.code,
            'description': cfg.description,
            'delay_value': cfg.delay_value,
            'delay_unit': cfg.delay_unit,
            'is_active': cfg.is_active,
            'delay_seconds': seconds,
            'delay_ms': seconds * 1000,
            'source': 'db',
        },
        status=status.HTTP_200_OK,
    )


#################################################
#           License Category                    #
#################################################

@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def license_category_list(request):
    """List all license categories."""
    queryset = masters_model.LicenseCategory.objects.all()
    serializer = LicenseCategorySerializer(queryset, many=True)
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'create')])
@api_view(['POST'])
def license_category_create(request):
    """Create a new license category."""
    serializer = LicenseCategorySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)

@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def license_category_detail(request, pk):
    """Retrieve a license category instance."""
    category = get_object_or_404(masters_model.LicenseCategory, pk=pk)
    serializer = LicenseCategorySerializer(category)
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'update')])
@api_view(['PUT', 'PATCH'])
def license_category_update(request, pk):
    """Update a license category instance."""
    category = get_object_or_404(masters_model.LicenseCategory, pk=pk)
    serializer = LicenseCategorySerializer(
        category, data=request.data, partial=request.method == 'PATCH'
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'delete')])
@api_view(['DELETE'])
def license_category_delete(request, pk):
    """Delete a license category instance."""
    category = get_object_or_404(masters_model.LicenseCategory, pk=pk)
    category.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


#################################################
#           License Type                        #
#################################################

@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def license_type_list(request):
    """List all license types."""
    queryset = masters_model.LicenseType.objects.all()
    serializer = LicenseTypeSerializer(queryset, many=True)
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'create')])
@api_view(['POST'])
def license_type_create(request):
    """Create a new license type."""
    serializer = LicenseTypeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)

@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def license_type_detail(request, pk):
    """Retrieve a license type instance."""
    license_type = get_object_or_404(masters_model.LicenseType, pk=pk)
    serializer = LicenseTypeSerializer(license_type)
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'update')])
@api_view(['PUT', 'PATCH'])
def license_type_update(request, pk):
    """Update a license type instance."""
    license_type = get_object_or_404(masters_model.LicenseType, pk=pk)
    serializer = LicenseTypeSerializer(
        license_type, data=request.data, partial=request.method == 'PATCH'
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'delete')])
@api_view(['DELETE'])
def license_type_delete(request, pk):
    """Delete a license type instance."""
    license_type = get_object_or_404(masters_model.LicenseType, pk=pk)
    license_type.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


#################################################
#           State                               #
#################################################

@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def state_list(request):
    """List all active states."""
    queryset = masters_model.State.objects.filter(is_active=True)
    serializer = StateSerializer(queryset, many=True, context={'request': request})
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'create')])
@api_view(['POST'])
def state_create(request):
    """Create a new state."""
    serializer = StateSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)

@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def state_detail(request, pk):
    """Retrieve an active state instance by primary key."""
    state = get_object_or_404(masters_model.State, pk=pk, is_active=True)
    serializer = StateSerializer(state, context={'request': request})
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'update')])
@api_view(['PUT', 'PATCH'])
def state_update(request, pk):
    """Update a state instance."""
    state = get_object_or_404(masters_model.State, pk=pk)
    serializer = StateSerializer(
        instance=state, data=request.data,
        partial=request.method == 'PATCH', context={'request': request}
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'delete')])
@api_view(['DELETE'])
def state_delete(request, pk):
    """Deactivate a state instance (soft delete)."""
    state = get_object_or_404(masters_model.State, pk=pk)
    state.is_active = False
    state.save()
    return Response(
        {'message': f'State {state.state} deactivated successfully.'},
        status=status.HTTP_200_OK
    )


#################################################
#           District                            #
#################################################

@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def district_list(request):
    """List all active districts, optionally filtered by state_code."""
    queryset = masters_model.District.objects.filter(is_active=True)
    state_code = request.query_params.get('state_code')
    if state_code:
        queryset = queryset.filter(state_code=state_code)
    serializer = DistrictSerializer(queryset, many=True, context={'request': request})
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'create')])
@api_view(['POST'])
def district_create(request):
    """Create a new district."""
    data = request.data.copy()
    data['state_code'] = 11  # Default state code for Sikkim
    serializer = DistrictSerializer(data=data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)

@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def district_detail(request, pk):
    """Retrieve an active district instance."""
    district = get_object_or_404(masters_model.District, pk=pk, is_active=True)
    serializer = DistrictSerializer(district, context={'request': request})
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'update')])
@api_view(['PUT', 'PATCH'])
def district_update(request, pk):
    """Update a district instance."""
    district = get_object_or_404(masters_model.District, pk=pk)
    serializer = DistrictSerializer(
        instance=district, data=request.data,
        partial=request.method == 'PATCH', context={'request': request}
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'delete')])
@api_view(['DELETE'])
def district_delete(request, pk):
    """Deactivate a district instance (soft delete)."""
    district = get_object_or_404(masters_model.District, pk=pk)
    if district.subdivisions.filter(is_active=True).exists():
        return Response(
            {"error": "Cannot deactivate district with active subdivisions."},
            status=status.HTTP_400_BAD_REQUEST
        )
    district.is_active = False
    district.save()
    return Response(
        {'message': f'District {district.district} deactivated successfully.'},
        status=status.HTTP_200_OK
    )


#################################################
#           Subdivision                         #
#################################################

@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def subdivision_list(request):
    """List all active subdivisions, optionally filtered by district_code."""
    queryset = masters_model.Subdivision.objects.filter(is_active=True)
    district_code = request.query_params.get('district_code')
    if district_code:
        queryset = queryset.filter(district_code=district_code)
    serializer = SubdivisionSerializer(queryset, many=True, context={'request': request})
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'create')])
@api_view(['POST'])
def subdivision_create(request):
    """Create a new subdivision."""
    serializer = SubdivisionSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)

@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def subdivision_detail(request, pk):
    """Retrieve an active subdivision instance."""
    subdivision = get_object_or_404(masters_model.Subdivision, pk=pk, is_active=True)
    serializer = SubdivisionSerializer(subdivision, context={'request': request})
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'update')])
@api_view(['PUT', 'PATCH'])
def subdivision_update(request, pk):
    """Update a subdivision instance."""
    subdivision = get_object_or_404(masters_model.Subdivision, pk=pk)
    serializer = SubdivisionSerializer(
        instance=subdivision, data=request.data,
        partial=request.method == 'PATCH', context={'request': request}
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'delete')])
@api_view(['DELETE'])
def subdivision_delete(request, pk):
    """Deactivate a subdivision instance (soft delete)."""
    subdivision = get_object_or_404(masters_model.Subdivision, pk=pk)
    if subdivision.police_stations.filter(is_active=True).exists():
        return Response(
            {"error": "Cannot deactivate subdivision with active police stations."},
            status=status.HTTP_400_BAD_REQUEST
        )
    subdivision.is_active = False
    subdivision.save()
    return Response(
        {'message': f'Subdivision {subdivision.subdivision} deactivated successfully.'},
        status=status.HTTP_200_OK
    )


#################################################
#           Police Station                      #
#################################################

@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def policestation_list(request):
    """List active police stations, optionally filtered by subdivision_code."""
    queryset = masters_model.PoliceStation.objects.filter(is_active=True)
    subdivision_code = request.query_params.get('subdivision_code')
    if subdivision_code:
        queryset = queryset.filter(subdivision_code=subdivision_code)
    serializer = PoliceStationSerializer(queryset, many=True, context={'request': request})
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'create')])
@api_view(['POST'])
def policestation_create(request):
    """Create a new police station."""
    serializer = PoliceStationSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)

@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def policestation_detail(request, pk):
    """Retrieve an active police station instance."""
    station = get_object_or_404(masters_model.PoliceStation, pk=pk, is_active=True)
    serializer = PoliceStationSerializer(station, context={'request': request})
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'update')])
@api_view(['PUT', 'PATCH'])
def policestation_update(request, pk):
    """Update a police station instance."""
    station = get_object_or_404(masters_model.PoliceStation, pk=pk)
    serializer = PoliceStationSerializer(
        instance=station, data=request.data,
        partial=request.method == 'PATCH', context={'request': request}
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'delete')])
@api_view(['DELETE'])
def policestation_delete(request, pk):
    """Deactivate a police station instance (soft delete)."""
    station = get_object_or_404(masters_model.PoliceStation, pk=pk)
    station.is_active = False
    station.save()
    return Response(
        {'message': f'Police Station {station.police_station} deactivated successfully.'},
        status=status.HTTP_200_OK
    )


#################################################
#           License Subcategory                 #
#################################################

@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def license_subcategory_list(request):
    """List all license subcategories, optionally filtered by ?category_id="""
    queryset = masters_model.LicenseSubcategory.objects.all()
    category_id = request.query_params.get('category_id')
    if category_id:
        queryset = queryset.filter(category_id=category_id)
    serializer = LicenseSubcategorySerializer(queryset, many=True, context={'request': request})
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'create')])
@api_view(['POST'])
def license_subcategory_create(request):
    """Create a new license subcategory."""
    serializer = LicenseSubcategorySerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)

@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def license_subcategory_detail(request, pk):
    """Retrieve a license subcategory by primary key."""
    subcategory = get_object_or_404(masters_model.LicenseSubcategory, pk=pk)
    serializer = LicenseSubcategorySerializer(subcategory, context={'request': request})
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'update')])
@api_view(['PUT', 'PATCH'])
def license_subcategory_update(request, pk):
    """Update an existing license subcategory."""
    subcategory = get_object_or_404(masters_model.LicenseSubcategory, pk=pk)
    serializer = LicenseSubcategorySerializer(
        instance=subcategory, data=request.data,
        partial=request.method == 'PATCH', context={'request': request}
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'delete')])
@api_view(['DELETE'])
def license_subcategory_delete(request, pk):
    """Delete a license subcategory (hard delete)."""
    subcategory = get_object_or_404(masters_model.LicenseSubcategory, pk=pk)
    subcategory.delete()
    return Response(
        {'message': f'License Subcategory "{subcategory.description}" deleted successfully.'},
        status=status.HTTP_200_OK
    )


#################################################
#               License Title                   #
#################################################

@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def license_title_list(request):
    """List all license titles."""
    queryset = masters_model.LicenseTitle.objects.all()
    serializer = LicenseTitleSerializer(queryset, many=True, context={'request': request})
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'create')])
@api_view(['POST'])
def license_title_create(request):
    """Create a new license title."""
    serializer = LicenseTitleSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)

@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def license_title_detail(request, pk):
    """Retrieve a license title by primary key."""
    title = get_object_or_404(masters_model.LicenseTitle, pk=pk)
    serializer = LicenseTitleSerializer(title, context={'request': request})
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'update')])
@api_view(['PUT', 'PATCH'])
def license_title_update(request, pk):
    """Update a license title."""
    title = get_object_or_404(masters_model.LicenseTitle, pk=pk)
    serializer = LicenseTitleSerializer(
        instance=title, data=request.data,
        partial=request.method == 'PATCH', context={'request': request}
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'delete')])
@api_view(['DELETE'])
def license_title_delete(request, pk):
    """Delete a license title (hard delete)."""
    title = get_object_or_404(masters_model.LicenseTitle, pk=pk)
    title.delete()
    return Response(
        {'message': f'License Title "{title.description}" deleted successfully.'},
        status=status.HTTP_200_OK
    )


#################################################
#                   Road                        #
#################################################

@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def road_list(request):
    """List all roads, optionally filtered by district_code."""
    queryset = masters_model.Road.objects.all()
    district_code = request.query_params.get('district_code')
    if district_code:
        queryset = queryset.filter(district_id=district_code)
    serializer = RoadSerializer(queryset, many=True, context={'request': request})
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'create')])
@api_view(['POST'])
def road_create(request):
    """Create a new road entry."""
    serializer = RoadSerializer(data=request.data, context={'request': request})
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)

@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def road_detail(request, pk):
    """Retrieve a road by primary key."""
    road = get_object_or_404(masters_model.Road, pk=pk)
    serializer = RoadSerializer(road, context={'request': request})
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'update')])
@api_view(['PUT', 'PATCH'])
def road_update(request, pk):
    """Update a road entry."""
    road = get_object_or_404(masters_model.Road, pk=pk)
    serializer = RoadSerializer(
        instance=road, data=request.data,
        partial=request.method == 'PATCH', context={'request': request}
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'delete')])
@api_view(['DELETE'])
def road_delete(request, pk):
    """Delete a road entry."""
    road = get_object_or_404(masters_model.Road, pk=pk)
    road.delete()
    return Response(
        {'message': f'Road "{road.road_name}" deleted successfully.'},
        status=status.HTTP_200_OK
    )


#################################################
#                   Location                    #
#################################################

@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def location_list(request):
    """List all active locations, optionally filtered by district_code."""
    queryset = masters_model.Location.objects.filter(is_active=True)
    district_code = request.query_params.get('district_code')
    if district_code:
        queryset = queryset.filter(district_code=district_code)
    serializer = LocationSerializer(queryset, many=True, context={'request': request})
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'create')])
@api_view(['POST'])
def location_create(request):
    """Create a new location."""
    serializer = LocationSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)

@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def location_detail(request, pk):
    """Retrieve an active location by primary key."""
    location = get_object_or_404(masters_model.Location, pk=pk, is_active=True)
    serializer = LocationSerializer(location, context={'request': request})
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'update')])
@api_view(['PUT', 'PATCH'])
def location_update(request, pk):
    """Update a location entry."""
    location = get_object_or_404(masters_model.Location, pk=pk)
    serializer = LocationSerializer(
        instance=location, data=request.data,
        partial=request.method == 'PATCH', context={'request': request}
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'delete')])
@api_view(['DELETE'])
def location_delete(request, pk):
    """Deactivate a location (soft delete)."""
    location = get_object_or_404(masters_model.Location, pk=pk)
    location.is_active = False
    location.save()
    return Response(
        {'message': f'Location "{location.location_description}" deactivated successfully.'},
        status=status.HTTP_200_OK
    )


#################################################
#               License Fee                     #
#################################################

@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def license_fee_list(request):
    """List all active license fees, optionally filtered by category, subcategory, or location."""
    queryset = masters_model.LicenseFee.objects.filter(is_active=True)
    category_id = request.query_params.get('license_category')
    subcategory_id = request.query_params.get('license_subcategory')
    location_code = request.query_params.get('location_code')
    if category_id:
        queryset = queryset.filter(license_category_id=category_id)
    if subcategory_id:
        queryset = queryset.filter(license_subcategory_id=subcategory_id)
    if location_code:
        queryset = queryset.filter(location_code=location_code)
    serializer = LicenseFeeSerializer(queryset, many=True, context={'request': request})
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'create')])
@api_view(['POST'])
def license_fee_create(request):
    """Create a new license fee entry."""
    serializer = LicenseFeeSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save(created_by=request.user)
    return Response(serializer.data, status=status.HTTP_201_CREATED)

@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def license_fee_detail(request, pk):
    """Retrieve an active license fee by primary key."""
    license_fee = get_object_or_404(masters_model.LicenseFee, pk=pk, is_active=True)
    serializer = LicenseFeeSerializer(license_fee, context={'request': request})
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'update')])
@api_view(['PUT', 'PATCH'])
def license_fee_update(request, pk):
    """Update a license fee entry."""
    license_fee = get_object_or_404(masters_model.LicenseFee, pk=pk)
    serializer = LicenseFeeSerializer(
        instance=license_fee, data=request.data,
        partial=request.method == 'PATCH', context={'request': request}
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'delete')])
@api_view(['DELETE'])
def license_fee_delete(request, pk):
    """Deactivate a license fee (soft delete)."""
    license_fee = get_object_or_404(masters_model.LicenseFee, pk=pk)
    license_fee.is_active = False
    license_fee.save()
    return Response(
        {'message': f'License Fee (ID: {license_fee.id}) deactivated successfully.'},
        status=status.HTTP_200_OK
    )


#################################################
#           Location Category                   #
#################################################

@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def locationcategory_list(request):
    """List all active location categories."""
    queryset = masters_model.LocationCategory.objects.filter(is_active=True)
    serializer = LocationCategorySerializer(queryset, many=True, context={'request': request})
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'create')])
@api_view(['POST'])
def locationcategory_create(request):
    """Create a new location category."""
    serializer = LocationCategorySerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)

@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def locationcategory_detail(request, pk):
    """Retrieve a location category instance."""
    category = get_object_or_404(masters_model.LocationCategory, pk=pk, is_active=True)
    serializer = LocationCategorySerializer(category, context={'request': request})
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'update')])
@api_view(['PUT', 'PATCH'])
def locationcategory_update(request, pk):
    """Update a location category instance."""
    category = get_object_or_404(masters_model.LocationCategory, pk=pk)
    serializer = LocationCategorySerializer(
        instance=category, data=request.data,
        partial=request.method == 'PATCH', context={'request': request}
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'delete')])
@api_view(['DELETE'])
def locationcategory_delete(request, pk):
    """Deactivate a location category (soft delete)."""
    category = get_object_or_404(masters_model.LocationCategory, pk=pk)
    category.is_active = False
    category.save()
    return Response(
        {'message': f'Location Category "{category.category_name}" deactivated successfully.'},
        status=status.HTTP_200_OK
    )


#################################################
#           Location Subcategory                #
#################################################

@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def locationsubcategory_list(request):
    """List all active location subcategories, optionally filtered by category."""
    queryset = masters_model.LocationSubcategory.objects.filter(is_active=True)
    category_id = request.query_params.get('category_id')
    if category_id:
        queryset = queryset.filter(category_id=category_id)
    serializer = LocationSubcategorySerializer(queryset, many=True, context={'request': request})
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'create')])
@api_view(['POST'])
def locationsubcategory_create(request):
    """Create a new location subcategory."""
    serializer = LocationSubcategorySerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)

@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def locationsubcategory_detail(request, pk):
    """Retrieve a location subcategory instance."""
    subcategory = get_object_or_404(masters_model.LocationSubcategory, pk=pk, is_active=True)
    serializer = LocationSubcategorySerializer(subcategory, context={'request': request})
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'update')])
@api_view(['PUT', 'PATCH'])
def locationsubcategory_update(request, pk):
    """Update a location subcategory instance."""
    subcategory = get_object_or_404(masters_model.LocationSubcategory, pk=pk)
    serializer = LocationSubcategorySerializer(
        instance=subcategory, data=request.data,
        partial=request.method == 'PATCH', context={'request': request}
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'delete')])
@api_view(['DELETE'])
def locationsubcategory_delete(request, pk):
    """Deactivate a location subcategory (soft delete)."""
    subcategory = get_object_or_404(masters_model.LocationSubcategory, pk=pk)
    subcategory.is_active = False
    subcategory.save()
    return Response(
        {'message': f'Location Subcategory "{subcategory.subcategory_name}" deactivated successfully.'},
        status=status.HTTP_200_OK
    )


#################################################
#           Ward                                #
#################################################

@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def ward_list(request):
    """List all active wards, optionally filtered by location_code."""
    queryset = masters_model.Ward.objects.filter(is_active=True)
    location_code = request.query_params.get('location_code')
    if location_code:
        queryset = queryset.filter(location_code=location_code)
    serializer = WardSerializer(queryset, many=True, context={'request': request})
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'create')])
@api_view(['POST'])
def ward_create(request):
    """Create a new ward."""
    serializer = WardSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)

@permission_classes([HasAppPermission('masters', 'view')])
@api_view(['GET'])
def ward_detail(request, pk):
    """Retrieve a ward instance."""
    ward = get_object_or_404(masters_model.Ward, pk=pk, is_active=True)
    serializer = WardSerializer(ward, context={'request': request})
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'update')])
@api_view(['PUT', 'PATCH'])
def ward_update(request, pk):
    """Update a ward instance."""
    ward = get_object_or_404(masters_model.Ward, pk=pk)
    serializer = WardSerializer(
        instance=ward, data=request.data,
        partial=request.method == 'PATCH', context={'request': request}
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)

@permission_classes([HasAppPermission('masters', 'delete')])
@api_view(['DELETE'])
def ward_delete(request, pk):
    """Deactivate a ward (soft delete)."""
    ward = get_object_or_404(masters_model.Ward, pk=pk)
    ward.is_active = False
    ward.save()
    return Response(
        {'message': f'Ward {ward.ward_number} - "{ward.ward_name}" deactivated successfully.'},
        status=status.HTTP_200_OK
    )
