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
        query parameters in the URL and the current user's licensee profile.
        """
        queryset = EnaCancellationDetail.objects.all().order_by('-created_at')
        
        try:
            if hasattr(self.request.user, 'supply_chain_profile'):
                 profile = self.request.user.supply_chain_profile
                 queryset = queryset.filter(licensee_id=profile.licensee_id)
        except Exception:
            pass

        our_ref_no = self.request.query_params.get('our_ref_no', None)
        status_param = self.request.query_params.get('status', None)
        
        if our_ref_no is not None:
            queryset = queryset.filter(our_ref_no__icontains=our_ref_no)
        if status_param is not None:
            queryset = queryset.filter(status=status_param)
            
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

                # Fetch Workflow/Stage for Cancellation (CN_00)
                from auth.workflow.models import Workflow, WorkflowStage
                # from models.masters.supply_chain.status_master.models import StatusMaster # Removed
                
                status_name = 'CancellationPending' # Default Initial Status
                wf_obj = None
                current_stage = None
                
                try:
                     # status_obj = StatusMaster.objects.get(status_code='CN_00') # Removed
                     # status_name = status_obj.status_name
                     
                     workflow = Workflow.objects.get(name='ENA Cancellation')
                     stage = WorkflowStage.objects.get(workflow=workflow, name=status_name)
                     
                     current_stage = stage
                     wf_obj = workflow
                except Exception as e:
                     print(f"Workflow setup warning: {e}")
                     # Fallback to defaults already set

                # Prepare Cancellation Data
                cancellation = EnaCancellationDetail(
                    our_ref_no=req.our_ref_no,
                    requisition_date=req.requisition_date,
                    grain_ena_number=req.grain_ena_number,         
                    bulk_spirit_type=req.bulk_spirit_type, 
                    strength=req.strength,
                    lifted_from=req.lifted_from,
                    via_route=req.via_route,
                    # Workflow fields
                    workflow=wf_obj,
                    current_stage=current_stage,
                    # Legacy fields
                    status=status_name,
                    status_code='CN_00',
                    
                    total_bl=req.totalbl,
                    requisiton_number_of_permits=req.requisiton_number_of_permits,
                    # Fields potentially missing in Requisition Model:
                    branch_name=req.lifted_from_distillery_name, 
                    branch_address="N/A", 
                    branch_purpose=req.branch_purpose,
                    govt_officer="N/A", 
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
                import traceback
                traceback.print_exc()
                return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='perform_action')
    def perform_action(self, request, pk=None):
        try:
            cancellation = self.get_object()
            action_type = request.data.get('action')
            remarks = request.data.get('remarks', f"Action {action_type} performed")
            
            # Use authenticated user from request
            user = request.user
            
            if not action_type:
                return Response({'error': 'Action is required'}, status=status.HTTP_400_BAD_REQUEST)

             # Determine Role
            user_role_name = user.role.name if hasattr(user, 'role') and user.role else None
            role_mapped = None
            commissioner_roles = ['level_1', 'level_2', 'level_3', 'level_4', 'level_5', 'Site-Admin', 'site_admin', 'commissioner', 'Commissioner']
            
            if user_role_name in commissioner_roles:
                role_mapped = 'commissioner'
            elif user_role_name in ['permit-section', 'Permit-Section', 'Permit Section']:
                role_mapped = 'permit-section'
            elif user_role_name in ['licensee', 'Licensee']:
                role_mapped = 'licensee'
            else:
                role_mapped = user_role_name
            
            from auth.workflow.services import WorkflowService
            
            # Ensure workflow/stage is set
            if not cancellation.workflow or not cancellation.current_stage:
                 from auth.workflow.models import Workflow, WorkflowStage
                 try:
                     wf = Workflow.objects.get(name='ENA Cancellation')
                     stage = WorkflowStage.objects.get(workflow=wf, name=cancellation.status)
                     cancellation.workflow = wf
                     cancellation.current_stage = stage
                     cancellation.save()
                 except Exception as e:
                     return Response({'error': f'Workflow state error: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Match Logic
            try:
                # Find Transition
                target_transition = None
                transitions = WorkflowService.get_next_stages(cancellation)
                
                for t in transitions:
                    # check role matches
                    role_match = False
                    if 'role' in t.condition:
                        if t.condition['role'] == role_mapped:
                            role_match = True
                    
                    # check action matches
                    action_match = False
                    if 'action' in t.condition:
                        if t.condition['action'] == action_type:
                            action_match = True
                            
                    if role_match and action_match:
                        target_transition = t
                        break
                
                if not target_transition:
                    return Response({
                        'error': f'Invalid action {action_type} for role {role_mapped} at stage {cancellation.current_stage.name}'
                    }, status=status.HTTP_400_BAD_REQUEST)

                WorkflowService.advance_stage(
                    application=cancellation,
                    user=user,
                    target_stage=target_transition.to_stage,
                    context={'role': role_mapped, 'action': action_type},
                    remarks=remarks
                )
                
                # Update status
                cancellation.status = target_transition.to_stage.name
                # cancellation.status_code = ... # Removed dependency
                cancellation.save()

                return Response({
                    'message': f'Action {action_type} performed successfully',
                    'new_status': cancellation.status,
                    'new_status_code': cancellation.status_code
                })

            except ValueError as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
            except PermissionError as e:
                return Response({'error': str(e)}, status=status.HTTP_403_FORBIDDEN)

        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
