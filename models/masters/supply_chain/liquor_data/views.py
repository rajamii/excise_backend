from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import F, Value, CharField
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import logging
from django.db import connection
from .models import LiquorData

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

class LiquorRatesView(APIView):
    def get(self, request):
        try:
            brand_name = request.query_params.get('brand_name')
            pack_size_ml = request.query_params.get('pack_size_ml')

            print(f"DEBUG: Received request - Brand: '{brand_name}', Size: '{pack_size_ml}'")

            if not brand_name or not pack_size_ml:
                return Response({
                    'success': False,
                    'error': 'Both brand_name and pack_size_ml are required parameters'
                }, status=status.HTTP_400_BAD_REQUEST)

            
            try:
                pack_size_ml = int(pack_size_ml)
            except ValueError:
                return Response({
                    'success': False,
                    'error': 'pack_size_ml must be a valid number'
                }, status=status.HTTP_400_BAD_REQUEST)

            
            with connection.cursor() as cursor:
                query = """
                    SELECT 
                        brand_name,
                        pack_size_ml,
                        education_cess_rs_per_case,  
                        excise_duty_rs_per_case,     
                        additional_excise_duty_rs_per_case  
                    FROM liquor_data_details 
                    WHERE brand_name ILIKE %s 
                    AND pack_size_ml = %s
                    LIMIT 1
                """
                cursor.execute(query, [brand_name.strip(), pack_size_ml])
                row = cursor.fetchone()

            print(f"DEBUG: Database query result: {row}")

            if not row:
                return Response({
                    'success': False,
                    'error': f'No data found for brand: {brand_name} and size: {pack_size_ml}ml'
                }, status=status.HTTP_404_NOT_FOUND)

            
            response_data = {
                'brand': row[0],
                'size': f"{row[1]}ml",
                'exFactoryPrice': 0,
                'educationCess': float(row[2] or 0), 
                'exciseDuty': float(row[3] or 0),
                'additionalExcise': float(row[4] or 0),
                'additionalExcise12_5': 0,
                'bottlingFee': 0,
                'exportFee': 0,
                'mrpPerBottle': 0,
                'totalPricePerCase': 0
            }

            print(f"DEBUG: Successfully returning: {response_data}")

            return Response({
                'success': True,
                'data': response_data
            })

        except Exception as e:
            print(f"DEBUG: Error occurred: {str(e)}")
            import traceback
            print(f"DEBUG: Traceback: {traceback.format_exc()}")
            return Response({
                'success': False,
                'error': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)