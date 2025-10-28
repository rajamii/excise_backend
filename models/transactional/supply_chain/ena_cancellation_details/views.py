from rest_framework import viewsets, permissions
from .models import EnaCancellationDetail
from .serializers import EnaCancellationDetailSerializer

class EnaCancellationDetailViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows ENA cancellation details to be viewed or edited.
    """
    queryset = EnaCancellationDetail.objects.all().order_by('-created_at')
    serializer_class = EnaCancellationDetailSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Optionally restricts the returned cancellations by filtering against
        query parameters in the URL.
        """
        queryset = EnaCancellationDetail.objects.all().order_by('-created_at')
        our_ref_no = self.request.query_params.get('our_ref_no', None)
        status = self.request.query_params.get('status', None)
        
        if our_ref_no is not None:
            queryset = queryset.filter(our_ref_no__icontains=our_ref_no)
        if status is not None:
            queryset = queryset.filter(status=status)
            
        return queryset
