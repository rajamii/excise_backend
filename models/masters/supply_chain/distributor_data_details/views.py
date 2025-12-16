# yourapp/views.py
import logging
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action, api_view
from django.shortcuts import get_object_or_404

from .models import TransitPermitDistributorData
from .serializers import TransitPermitDistributorDataSerializer

logger = logging.getLogger(__name__)

class TransitPermitDistributorDataViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows distributor data to be viewed or edited.
    Wrapped list() to return JSON and log exceptions in dev (prevents HTML error pages).
    """
    queryset = TransitPermitDistributorData.objects.all().order_by('id')
    serializer_class = TransitPermitDistributorDataSerializer

    def get_queryset(self):
        """
        Optionally filter the distributor data by manufacturing unit or distributor name.
        Query params:
          - manufacturing_unit (partial match)
          - distributor_name (partial match)
        """
        queryset = super().get_queryset()
        manufacturing_unit = self.request.query_params.get('manufacturing_unit', None)
        distributor_name = self.request.query_params.get('distributor_name', None)

        if manufacturing_unit:
            queryset = queryset.filter(manufacturing_unit__icontains=manufacturing_unit)
        if distributor_name:
            queryset = queryset.filter(distributor_name__icontains=distributor_name)

        return queryset

    # DEV: catch exceptions in list() and return JSON instead of HTML (so frontend JSON.parse won't fail)
    def list(self, request, *args, **kwargs):
        try:
            return super().list(request, *args, **kwargs)
        except Exception as e:
            logger.exception("Exception in distributor-data list endpoint")
            # Return JSON error (dev only). In prod, you may want to re-raise or return 500 with safe message.
            return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def search(self, request):
        """
        Custom search endpoint for distributor data (alias of list with filter).
        """
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

# Temporary sample endpoint (dev only) to quickly return JSON for frontend testing:
@api_view(['GET'])
def distributor_data_sample(request):
    sample = [
        {"id": 1, "distributorName": "Sample Distributor A", "depoAddress": "12 Depot Road, City", "manufacturingUnit": "Unit A"},
        {"id": 2, "distributorName": "Sample Distributor B", "depoAddress": "34 Depot Lane, City", "manufacturingUnit": "Unit B"},
    ]
    return Response(sample)

# Debug endpoint to test database connection
@api_view(['GET'])
def distributor_data_debug(request):
    try:
        # Try to get raw data from database
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM transit_permit_distributor_data LIMIT 5")
            rows = cursor.fetchall()
            columns = [col[0] for col in cursor.description]
            
            # Convert to list of dictionaries
            data = []
            for row in rows:
                data.append(dict(zip(columns, row)))
            
            return Response({
                'success': True,
                'count': len(data),
                'columns': columns,
                'data': data
            })
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        })
