from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import BrandOwner, BrandOwnerFee, BrandOwnerType, LiquorBrand, LiquorKind, LiquorType, LiquorCategory, master_Brand_owner
from .serializers import (
    BrandOwnerFeeSerializer,
    BrandOwnerSerializer,
    BrandOwnerTypeSerializer,
    LiquorBrandSerializer,
    LiquorCategorySerializer,
    LiquorKindSerializer,
    LiquorTypeSerializer,
)


def _category_row(code):
    try:
        cat = LiquorCategory.objects.get(pk=code)
        desc = cat.liquor_cat_desc
        abbr = cat.liquor_cat_abbr
    except LiquorCategory.DoesNotExist:
        desc = f'Category {code}'
        abbr = str(code)
    return {
        'liquor_cat_code': code,
        'liquor_cat_desc': desc,
        'liquor_cat_abbr': abbr,
        'delete_status': 'N',
    }


def _type_row(row):
    type_id = row['liquor_type']
    cat = row['liquor_cat']
    kind_id = row['liquor_kind']
    try:
        lt = LiquorType.objects.get(liquor_cat=cat, liquor_kind_id=kind_id, liquor_type_code=type_id)
        desc = lt.liquor_type_desc
    except LiquorType.DoesNotExist:
        desc = f'Type {type_id}'
    return {
        'id': type_id,
        'liquor_cat': cat,
        'liquor_kind': kind_id,
        'liquor_type_code': type_id,
        'liquor_type_desc': desc,
        'delete_status': 'N',
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_brand_owner_types(request):
    return Response(BrandOwnerTypeSerializer(BrandOwnerType.objects.all(), many=True).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_brand_owners(request):
    qs = master_Brand_owner.objects.filter(Delete_Status='N')
    type_code = request.query_params.get('type')
    if type_code:
        qs = qs.filter(Brand_Owner_Type_Code=type_code)
    return Response(BrandOwnerSerializer(qs, many=True).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def brand_owner_detail(request, brand_owner_code):
    try:
        obj = master_Brand_owner.objects.get(pk=brand_owner_code)
    except master_Brand_owner.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)
    return Response(BrandOwnerSerializer(obj).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_brand_owner(request):
    serializer = BrandOwnerSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=201)
    return Response(serializer.errors, status=400)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_brand_owner(request, brand_owner_code):
    try:
        obj = master_Brand_owner.objects.get(pk=brand_owner_code)
    except master_Brand_owner.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)
    
    serializer = BrandOwnerSerializer(obj, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=400)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_brand_owner(request, brand_owner_code):
    try:
        obj = master_Brand_owner.objects.get(pk=brand_owner_code)
    except master_Brand_owner.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)
    
    obj.Delete_Status = 'Y'
    obj.save()
    return Response({'detail': 'Deleted successfully.'}, status=204)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_liquor_categories(request):
    codes = (
        LiquorKind.objects
        .filter(delete_status='N')
        .order_by('liquor_cat')
        .values_list('liquor_cat', flat=True)
        .distinct()
    )
    data = [_category_row(code) for code in codes]
    return Response(LiquorCategorySerializer(data, many=True).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_liquor_kinds(request):
    qs = LiquorKind.objects.filter(delete_status='N')
    cat_code = request.query_params.get('cat')
    if cat_code:
        qs = qs.filter(liquor_cat=cat_code)
    return Response(LiquorKindSerializer(qs, many=True).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_liquor_types(request):
    qs = LiquorBrand.objects.filter(delete_status='N')
    cat_code = request.query_params.get('cat')
    kind_id  = request.query_params.get('kind')
    if cat_code:
        qs = qs.filter(liquor_cat=cat_code)
    if kind_id:
        qs = qs.filter(liquor_kind=kind_id)
    rows = (
        qs.order_by('liquor_cat', 'liquor_kind', 'liquor_type')
        .values('liquor_cat', 'liquor_kind', 'liquor_type')
        .distinct()
    )
    data = [_type_row(row) for row in rows]
    return Response(LiquorTypeSerializer(data, many=True).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_liquor_brands(request):
    qs = LiquorBrand.objects.filter(delete_status='N').select_related('liquor_kind')
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
    from models.masters.core.models import MasterFixedFee
    fee_obj = MasterFixedFee.objects.filter(
        fee_code='COMP_COLLAB_FEE',
        is_active=True,
    ).first()
    if not fee_obj:
        return Response({'detail': 'No active collaboration fee found.'}, status=404)

    return Response({
        'collaborationFee': str(fee_obj.amount),
    })
