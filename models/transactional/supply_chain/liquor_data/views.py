from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import F, Value, CharField
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import logging
from django.db import connection

logger = logging.getLogger(__name__)

class BrandSizeListView(APIView):
    def get(self, request):
        try:
            # First, get all unique brand names
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT DISTINCT brand_name 
                    FROM liquor_data_details 
                    WHERE brand_name IS NOT NULL
                """)
                brand_names = [row[0] for row in cursor.fetchall()]
            
            result = []
            
            # For each brand, get its sizes
            for brand_name in brand_names:
                if not brand_name:
                    continue
                    
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT DISTINCT pack_size_ml 
                        FROM liquor_data_details 
                        WHERE brand_name = %s 
                        AND pack_size_ml IS NOT NULL
                        ORDER BY pack_size_ml
                    """, [brand_name])
                    sizes = [row[0] for row in cursor.fetchall()]
                
                if sizes:
                    result.append({
                        'brandName': brand_name,
                        'sizes': sizes
                    })
            
            # Sort by brand name
            result.sort(key=lambda x: x['brandName'])
            
            return Response({
                'success': True,
                'data': result
            })
            
        except Exception as e:
            logger.error(f"Error in BrandSizeListView: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
