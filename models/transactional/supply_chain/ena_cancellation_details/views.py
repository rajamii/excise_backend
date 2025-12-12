from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from .models import EnaCancellationDetail
from .serializers import EnaCancellationDetailSerializer, CancellationCreateSerializer

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

    @action(detail=False, methods=['post'], url_path='submit')
    def submit_cancellation(self, request):
        serializer = CancellationCreateSerializer(data=request.data)
        if serializer.is_valid():
            ref_no = serializer.validated_data['referenceNo']
            permit_numbers = serializer.validated_data['permitNumbers']
            licensee_id = serializer.validated_data['licenseeId']

            try:
                # Fetch Requisition Data
                from models.transactional.supply_chain.ena_requisition_details.models import EnaRequisitionDetail
                req = EnaRequisitionDetail.objects.filter(our_ref_no=ref_no).first()

                if not req:
                    return Response({'error': 'Requisition not found'}, status=status.HTTP_404_NOT_FOUND)

                # Calculate Amount
                cancellation_charge_per_permit = 1000
                total_amount = len(permit_numbers) * cancellation_charge_per_permit

                # Prepare Cancellation Data (Mapping fields)
                # Note: Handling potential missing fields with defaults
                cancellation = EnaCancellationDetail(
                    our_ref_no=req.our_ref_no,
                    requisition_date=req.requisition_date,
                    grain_ena_number=req.grain_ena_number,         
                    # Strength fields mismatch handling - defaulting to 0 if parsing fails or not present
                    strength_from=0.00, 
                    strength_to=0.00,
                    lifted_from=req.lifted_from,
                    via_route=req.via_route,
                    status='CN_00', # CancellationPending
                    total_bl=req.totalbl,
                    requisiton_number_of_permits=req.requisiton_number_of_permits,
                    # Fields potentially missing in Requisition Model:
                    branch_name="N/A", # Placeholder as not in Requisition model shown
                    branch_address="N/A", # Placeholder
                    branch_purpose=req.branch_purpose,
                    govt_officer="N/A", # Placeholder
                    state=req.state,
                    cancellation_date=timezone.now(),
                    cancellation_br_amount=0.00,
                    cancelled_permit_number=",".join(permit_numbers),
                    total_cancellation_amount=total_amount,
                    permit_nocount=str(len(permit_numbers)),
                    licensee_id=licensee_id,
                    distillery_name=req.lifted_from_distillery_name
                )
                
                cancellation.save()
                
                return Response({'message': 'Cancellation request submitted successfully!', 'id': cancellation.id}, status=status.HTTP_201_CREATED)

            except Exception as e:
                return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
