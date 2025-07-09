 # views/user_activity_views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import get_user_model
from auth.roles.permissions import HasAppPermission
from .models import UserActivity
from .serializer import UserActivitySerializer

User = get_user_model()

@api_view(['GET'])
@permission_classes([HasAppPermission('logs', 'view')])
def user_activity_list(request):
    user_id = request.query_params.get('user_id')
    activity_type = request.query_params.get('type')
    
    queryset = UserActivity.objects.all()
    
    if user_id:
        queryset = queryset.filter(user__id=user_id)
    if activity_type:
        queryset = queryset.filter(activity_type=activity_type)
    
    serializer = UserActivitySerializer(
        queryset.order_by('-timestamp')[:100],  # Limit to 100 most recent
        many=True
    )
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([HasAppPermission('logs', 'create')])
def track_custom_activity(request):
    serializer = UserActivitySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)
