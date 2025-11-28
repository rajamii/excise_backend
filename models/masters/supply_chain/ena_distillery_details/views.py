import logging
import logging
import traceback
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import enaDistilleryTypes

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)

class enaDistilleryTypesListAPIView(APIView):
    """
    API view to list all distillery types with their via routes.
    """
    def get(self, request, format=None):
        try:
            # Debug: Check if we can query the model
            from django.apps import apps
            from django.db import connection
            
            # Log available models and database tables
            logger.info(f"Available models: {[m.__name__ for m in apps.get_models()]}")
            logger.info(f"Database tables: {connection.introspection.table_names()}")
            
            # Query all distillery types with explicit database routing
            distilleries = enaDistilleryTypes.objects.using('default').all()
            logger.info(f"Found {distilleries.count()} distilleries")
            
            # Convert queryset to list to ensure evaluation
            distilleries_list = list(distilleries)
            logger.info(f"Distilleries list length: {len(distilleries_list)}")
            
            # Prepare the response data
            data = [{
                'id': distillery.id,
                'distillery_name': distillery.distillery_name,
                'via_route': distillery.via_route,
                'state': distillery.distillery_state
            } for distillery in distilleries_list]
            
            logger.info(f"First distillery (if any): {data[0] if data else 'No data'}")
            
            return Response({
                'success': True,
                'count': len(data),
                'data': data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error in enaDistilleryTypesListAPIView: {str(e)}\n{traceback.format_exc()}")
            return Response({
                'success': False,
                'message': 'An error occurred while fetching distillery types.',
                'error': str(e),
                'traceback': traceback.format_exc()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
