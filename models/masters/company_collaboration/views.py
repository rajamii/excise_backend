from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import BrandOwner, BrandOwnerFee, BrandOwnerType, LiquorBrand, LiquorKind, LiquorType, LiquorCategory, master_Brand_owner, LiquorProduct
from .serializers import (
    BrandOwnerFeeSerializer,
    BrandOwnerSerializer,
    BrandOwnerTypeSerializer,
    LiquorBrandSerializer,
    LiquorCategorySerializer,
    LiquorKindSerializer,
    LiquorTypeSerializer,
    CompanyDetailSerializer,
    LiquorCategoryCRUDSerializer,
    LiquorKindCRUDSerializer,
    LiquorTypeCRUDSerializer,
    LiquorBrandCRUDSerializer,
)
from django.db.models import Q


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


# ── Company Details (Original BrandOwner) CRUD ────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_company_details(request):
    qs = BrandOwner.objects.all().select_related('brand_owner_type')
    type_code = request.query_params.get('type')
    if type_code:
        qs = qs.filter(brand_owner_type=type_code)
    return Response(CompanyDetailSerializer(qs, many=True).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def company_detail_detail(request, brand_owner_code):
    try:
        obj = BrandOwner.objects.select_related('brand_owner_type').get(pk=brand_owner_code)
    except BrandOwner.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)
    return Response(CompanyDetailSerializer(obj).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_company_detail(request):
    serializer = CompanyDetailSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=201)
    return Response(serializer.errors, status=400)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_company_detail(request, brand_owner_code):
    try:
        obj = BrandOwner.objects.get(pk=brand_owner_code)
    except BrandOwner.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)
    
    serializer = CompanyDetailSerializer(obj, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=400)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_company_detail(request, brand_owner_code):
    try:
        obj = BrandOwner.objects.get(pk=brand_owner_code)
    except BrandOwner.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)
    
    obj.delete()
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


# ── Liquor Category CRUD ──────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_categories_crud(request):
    qs = LiquorCategory.objects.filter(delete_status='N')
    return Response(LiquorCategoryCRUDSerializer(qs, many=True).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_category_crud(request):
    serializer = LiquorCategoryCRUDSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=201)
    return Response(serializer.errors, status=400)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_category_crud(request, pk):
    try:
        obj = LiquorCategory.objects.get(pk=pk)
    except LiquorCategory.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)
    serializer = LiquorCategoryCRUDSerializer(obj, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=400)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_category_crud(request, pk):
    try:
        obj = LiquorCategory.objects.get(pk=pk)
    except LiquorCategory.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)
    obj.delete_status = 'Y'
    obj.save()
    return Response({'detail': 'Deleted successfully.'}, status=204)


# ── Liquor Kind CRUD ──────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_kinds_crud(request):
    qs = LiquorKind.objects.filter(delete_status='N')
    return Response(LiquorKindCRUDSerializer(qs, many=True).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_kind_crud(request):
    serializer = LiquorKindCRUDSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=201)
    return Response(serializer.errors, status=400)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_kind_crud(request, pk):
    try:
        obj = LiquorKind.objects.get(pk=pk)
    except LiquorKind.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)
    serializer = LiquorKindCRUDSerializer(obj, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=400)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_kind_crud(request, pk):
    try:
        obj = LiquorKind.objects.get(pk=pk)
    except LiquorKind.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)
    obj.delete_status = 'Y'
    obj.save()
    return Response({'detail': 'Deleted successfully.'}, status=204)


# ── Liquor Type CRUD ──────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_types_crud(request):
    qs = LiquorType.objects.filter(delete_status='N').select_related('liquor_kind')
    return Response(LiquorTypeCRUDSerializer(qs, many=True).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_type_crud(request):
    serializer = LiquorTypeCRUDSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=201)
    return Response(serializer.errors, status=400)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_type_crud(request, pk):
    try:
        obj = LiquorType.objects.get(pk=pk)
    except LiquorType.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)
    serializer = LiquorTypeCRUDSerializer(obj, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=400)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_type_crud(request, pk):
    try:
        obj = LiquorType.objects.get(pk=pk)
    except LiquorType.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)
    obj.delete_status = 'Y'
    obj.save()
    return Response({'detail': 'Deleted successfully.'}, status=204)


# ── Liquor Brand CRUD ─────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_brands_crud(request):
    search = request.query_params.get('search', '').strip()
    if not search:
        return Response([])
    
    qs = LiquorBrand.objects.filter(delete_status='N').select_related('liquor_kind')
    
    # Split search into tokens and apply AND logic: all tokens must match somewhere
    tokens = search.split()
    for token in tokens:
        qs = qs.filter(
            Q(liquor_brand_desc__icontains=token) | Q(liquor_brand_code__icontains=token)
        )
    
    return Response(LiquorBrandCRUDSerializer(qs[:100], many=True).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_brand_crud(request):
    serializer = LiquorBrandCRUDSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=201)
    return Response(serializer.errors, status=400)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_brand_crud(request, pk):
    try:
        obj = LiquorBrand.objects.get(pk=pk)
    except LiquorBrand.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)
    serializer = LiquorBrandCRUDSerializer(obj, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=400)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_brand_crud(request, pk):
    try:
        obj = LiquorBrand.objects.get(pk=pk)
    except LiquorBrand.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)
    obj.delete_status = 'Y'
    obj.save()
    return Response({'detail': 'Deleted successfully.'}, status=204)


# ── Brand Pack Sizes (ML from master_liquor_product) ──────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def brand_pack_sizes(request, brand_code):
    """
    Return distinct pack sizes for a brand from master_liquor_product.
    brand_code is URL-encoded since it may contain '/'
    """
    import urllib.parse
    brand_code = urllib.parse.unquote(brand_code)
    sizes = (
        LiquorProduct.objects
        .filter(liquor_brand_code=brand_code, delete_status='N')
        .exclude(measure_value__isnull=True)
        .values('id', 'measure_value', 'measure_unit')
        .distinct()
        .order_by('measure_value')
    )
    data = [
        {
            'id': s['id'],
            'measureValue': s['measure_value'],
            'measureUnit': s['measure_unit'] or 'Ml',
            'label': f"{s['measure_value']} Ml"
        }
        for s in sizes
    ]
    return Response(data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_brand_pack_size(request, brand_code):
    """
    Add a pack size for a brand in master_liquor_product.
    Expects: { measureValue: 750 }
    """
    import urllib.parse
    brand_code = urllib.parse.unquote(brand_code)
    measure_value = request.data.get('measureValue') or request.data.get('measure_value')
    if not measure_value:
        return Response({'detail': 'measureValue is required.'}, status=400)
    
    # Check if already exists
    already = LiquorProduct.objects.filter(
        liquor_brand_code=brand_code,
        measure_value=measure_value,
        delete_status='N'
    ).exists()
    if already:
        return Response({'detail': 'This pack size already exists for this brand.'}, status=400)
    
    # Get the brand details to copy liquor_cat/kind/type
    try:
        brand = LiquorBrand.objects.get(liquor_brand_code=brand_code, delete_status='N')
    except LiquorBrand.DoesNotExist:
        return Response({'detail': 'Brand not found.'}, status=404)
    except LiquorBrand.MultipleObjectsReturned:
        brand = LiquorBrand.objects.filter(liquor_brand_code=brand_code, delete_status='N').first()
    
    prod = LiquorProduct.objects.create(
        liquor_brand_code=brand_code,
        liquor_cat_code=brand.liquor_cat,
        liquor_kind_code=brand.liquor_kind_id,
        liquor_type_code=brand.liquor_type,
        measure_value=measure_value,
        measure_unit='M',
        delete_status='N',
        entry_flag='Y',
    )
    return Response({
        'id': prod.id,
        'measureValue': prod.measure_value,
        'measureUnit': prod.measure_unit,
        'label': f"{prod.measure_value} Ml"
    }, status=201)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_brand_pack_size(request, size_id):
    """
    Soft-delete a pack size record from master_liquor_product.
    """
    try:
        prod = LiquorProduct.objects.get(pk=size_id)
    except LiquorProduct.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=404)
    prod.delete_status = 'Y'
    prod.save()
    return Response({'detail': 'Pack size removed.'}, status=204)
