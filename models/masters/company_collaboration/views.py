from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import BrandOwner, BrandOwnerFee, BrandOwnerType, LiquorBrand, LiquorCategory, LiquorKind, LiquorType
from .serializers import (
    BrandOwnerFeeSerializer,
    BrandOwnerSerializer,
    BrandOwnerTypeSerializer,
    LiquorBrandSerializer,
    LiquorCategorySerializer,
    LiquorKindSerializer,
    LiquorTypeSerializer,
)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_brand_owner_types(request):
    return Response(BrandOwnerTypeSerializer(BrandOwnerType.objects.all(), many=True).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_brand_owners(request):
    qs = BrandOwner.objects.filter(enable_status='E').select_related('brand_owner_type')
    type_code = request.query_params.get('type')
    if type_code:
        qs = qs.filter(brand_owner_type=type_code)
    return Response(BrandOwnerSerializer(qs, many=True).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def brand_owner_detail(request, brand_owner_code):
    try:
        obj = BrandOwner.objects.select_related('brand_owner_type').get(pk=brand_owner_code)
    except BrandOwner.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)
    return Response(BrandOwnerSerializer(obj).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_liquor_categories(request):
    qs = LiquorCategory.objects.filter(delete_status='N')
    return Response(LiquorCategorySerializer(qs, many=True).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_liquor_kinds(request):
    qs = LiquorKind.objects.filter(delete_status='N').select_related('liquor_cat')
    cat_code = request.query_params.get('cat')
    if cat_code:
        qs = qs.filter(liquor_cat=cat_code)
    return Response(LiquorKindSerializer(qs, many=True).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_liquor_types(request):
    qs = LiquorType.objects.filter(delete_status='N').select_related('liquor_cat', 'liquor_kind')
    cat_code = request.query_params.get('cat')
    kind_id  = request.query_params.get('kind')
    if cat_code:
        qs = qs.filter(liquor_cat=cat_code)
    if kind_id:
        qs = qs.filter(liquor_kind=kind_id)
    return Response(LiquorTypeSerializer(qs, many=True).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_liquor_brands(request):
    qs = LiquorBrand.objects.filter(delete_status='N').select_related('liquor_cat', 'liquor_kind', 'liquor_type')
    cat_code = request.query_params.get('cat')
    kind_id  = request.query_params.get('kind')
    type_id  = request.query_params.get('type')
    if cat_code:
        qs = qs.filter(liquor_cat=cat_code)
    if kind_id:
        qs = qs.filter(liquor_kind=kind_id)
    if type_id:
        qs = qs.filter(liquor_type=type_id)
    return Response(LiquorBrandSerializer(qs, many=True).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def active_fee(request):
    fee = BrandOwnerFee.objects.filter(active_status='A').order_by('-from_date').first()
    if not fee:
        return Response({'detail': 'No active fee structure found.'}, status=404)
    return Response(BrandOwnerFeeSerializer(fee).data)
