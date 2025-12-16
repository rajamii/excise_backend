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

    @action(detail=False, methods=['post'], url_path='submit', serializer_class=CancellationCreateSerializer)
    def submit_cancellation(self, request):
        print("Received Data:", request.data)
        serializer = CancellationCreateSerializer(data=request.data)
        if serializer.is_valid():
            ref_no = serializer.validated_data['reference_no']
            permit_numbers = serializer.validated_data['permit_numbers']
            licensee_id = serializer.validated_data['licensee_id']

            try:
                # Fetch Requisition Data
                from models.transactional.supply_chain.ena_requisition_details.models import EnaRequisitionDetail
                req = EnaRequisitionDetail.objects.filter(our_ref_no=ref_no).first()

                if not req:
                    return Response({'error': 'Requisition not found'}, status=status.HTTP_404_NOT_FOUND)

                # Calculate Amount
                cancellation_charge_per_permit = 1000
                total_amount = len(permit_numbers) * cancellation_charge_per_permit

                # Fetch Status
                try:
                    from models.masters.supply_chain.status_master.models import StatusMaster
                    status_obj = StatusMaster.objects.get(status_code='CN_00')
                    status_name = status_obj.status_name
                except Exception:
                    # Fallback if master data missing
                    status_name = 'CancellationPending'
                
                # Prepare Cancellation Data (Mapping fields)
                # Note: Handling potential missing fields with defaults
                cancellation = EnaCancellationDetail(
                    our_ref_no=req.our_ref_no,
                    requisition_date=req.requisition_date,
                    grain_ena_number=req.grain_ena_number,         
                    bulk_spirit_type=req.bulk_spirit_type, 
                    strength=req.strength,
                    lifted_from=req.lifted_from,
                    via_route=req.via_route,
                    status=status_name,
                    status_code='CN_00',
                    total_bl=req.totalbl,
                    requisiton_number_of_permits=req.requisiton_number_of_permits,
                    # Fields potentially missing in Requisition Model:
                    branch_name=req.lifted_from_distillery_name, # Mapping distillery name to branch name as fallback
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

    @action(detail=True, methods=['post'], url_path='perform_action')
    def perform_action(self, request, pk=None):
        try:
            cancellation = self.get_object()
            action = request.data.get('action')
            role = request.data.get('role', 'permit-section') # Default for dev/testing

            if not action:
                return Response({'error': 'Action is required'}, status=status.HTTP_400_BAD_REQUEST)

            # Fetch current status and rule
            from models.masters.supply_chain.status_master.models import StatusMaster, WorkflowRule
            
            # Find the rule
            try:
                rule = WorkflowRule.objects.get(
                    current_status__status_code=cancellation.status_code,
                    action=action,
                    allowed_role=role
                )
            except WorkflowRule.DoesNotExist:
                return Response({'error': 'Invalid action or permission denied'}, status=status.HTTP_403_FORBIDDEN)

            # Update Status
            cancellation.status = rule.next_status.status_name
            cancellation.status_code = rule.next_status.status_code
            
            # If rejected, maybe capture reason? (Optional enhancement)
            
            cancellation.save()

            return Response({
                'message': f'Action {action} performed successfully',
                'new_status': cancellation.status,
                'new_status_code': cancellation.status_code
            })

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
