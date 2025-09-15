from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from .serializers import TransactionDataSerializer
from .models import TransactionData
from django.shortcuts import get_object_or_404

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_transaction(request):
    serializer = TransactionDataSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save(licensee_id=request.user, updated_by=request.user)  # Set both licensee_id and updated_by
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
def list_transactions(request):
    transactions = TransactionData.objects.all()
    data = [{
        'id': transaction.id,
        'licensee_id': transaction.licensee_id.id,
        'district': {
            'district_code': transaction.district.district_code,
            'district_name': transaction.district.district
        },
        'subdivision': {
            'subdivision_code': transaction.subdivision.subdivision_code,
            'subdivision_name': transaction.subdivision.subdivision
        },
        'license_category': {
            'id': transaction.license_category.id,
            'name': transaction.license_category.license_category
        } if transaction.license_category else None,
        'longitude': float(transaction.longitude),
        'latitude': float(transaction.latitude),
        'file': transaction.file.url if transaction.file else None,
        'created_at': transaction.created_at.isoformat(),
        'updated_by': transaction.updated_by.username if transaction.updated_by else None
    } for transaction in transactions]
    return Response(data, status=status.HTTP_200_OK)

@api_view(['GET'])
def transaction_detail(request, transaction_id):
    transaction = get_object_or_404(TransactionData, id=transaction_id)
    data = {
        'id': transaction.id,
        'licensee_id': transaction.licensee_id.id,
        'district': {
            'district_code': transaction.district.district_code,
            'district_name': transaction.district.district
        },
        'subdivision': {
            'subdivision_code': transaction.subdivision.subdivision_code,
            'subdivision_name': transaction.subdivision.subdivision
        },
        'license_category': {
            'id': transaction.license_category.id,
            'name': transaction.license_category.license_category
        } if transaction.license_category else None,
        'longitude': float(transaction.longitude),
        'latitude': float(transaction.latitude),
        'file': transaction.file.url if transaction.file else None,
        'created_at': transaction.created_at.isoformat(),
        'updated_by': transaction.updated_by.username if transaction.updated_by else None
    }
    return Response(data, status=status.HTTP_200_OK)

@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_transaction(request, transaction_id):
    transaction = get_object_or_404(TransactionData, id=transaction_id)
    serializer = TransactionDataSerializer(transaction, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save(updated_by=request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_transaction(request, transaction_id):
    transaction = get_object_or_404(TransactionData, id=transaction_id)
    transaction.delete()
    return Response({'message': f'Transaction {transaction_id} deleted successfully'}, status=status.HTTP_204_NO_CONTENT)

@api_view(['GET'])
def count_transactions(request):
    count = TransactionData.objects.count()
    return Response({
        'message': 'Transaction count retrieved successfully',
        'count': count
    }, status=status.HTTP_200_OK)