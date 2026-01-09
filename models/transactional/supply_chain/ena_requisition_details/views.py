from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import re
from .models import EnaRequisitionDetail
from .serializers import EnaRequisitionDetailSerializer


class EnaRequisitionDetailListCreateAPIView(generics.ListCreateAPIView):
    queryset = EnaRequisitionDetail.objects.all()
    serializer_class = EnaRequisitionDetailSerializer

    def get_queryset(self):
        queryset = EnaRequisitionDetail.objects.all()
        
        # Filter by Licensee ID if user has a profile
        try:
            if hasattr(self.request.user, 'supply_chain_profile'):
                 profile = self.request.user.supply_chain_profile
                 queryset = queryset.filter(licensee_id=profile.licensee_id)
        except Exception:
            pass # Or handle specific roles if needed

        our_ref_no = self.request.query_params.get('our_ref_no', None)
        if our_ref_no is not None:
            queryset = queryset.filter(our_ref_no=our_ref_no)
        return queryset


class EnaRequisitionDetailRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = EnaRequisitionDetail.objects.all()
    serializer_class = EnaRequisitionDetailSerializer


class GetNextRefNumberAPIView(APIView):
    """
    API endpoint to generate the next unique reference number.
    Format: IBPS/{number:02d}/EXCISE
    
    Logic:
    - Queries all existing our_ref_no values
    - Extracts numeric parts and finds the maximum
    - Returns next sequential number
    - If all records are deleted, restarts from 1
    """
    def get(self, request):
        try:
            # Get all existing reference numbers
            existing_refs = EnaRequisitionDetail.objects.values_list('our_ref_no', flat=True)
            
            # Extract numeric parts from reference numbers
            numbers = []
            pattern = r'IBPS/(\d+)/EXCISE'
            
            for ref in existing_refs:
                match = re.match(pattern, ref)
                if match:
                    numbers.append(int(match.group(1)))
            
            # Determine next number
            if numbers:
                next_number = max(numbers) + 1
            else:
                next_number = 1
            
            # Format the reference number
            ref_number = f"IBPS/{next_number:02d}/EXCISE"
            
            return Response({
                'status': 'success',
                'ref_number': ref_number,
                'next_sequence': next_number
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PerformRequisitionActionAPIView(APIView):
    """
    API endpoint to perform an action (APPROVE/REJECT) on a requisition.
    Dynamically determines the next status based on the current status and the action
    by querying the WorkflowRule table.
    """
    def post(self, request, pk):
        try:
             # from models.masters.supply_chain.status_master.models import StatusMaster, WorkflowRule # Removed
            
            action = request.data.get('action')
            if not action or action not in ['APPROVE', 'REJECT']:
                return Response({
                    'status': 'error',
                    'message': 'Valid action (APPROVE or REJECT) is required'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Get the requisition
            requisition = EnaRequisitionDetail.objects.get(pk=pk)
            current_status_code = requisition.status_code
            
            # Determine User Role
            user_role_name = request.user.role.name if hasattr(request.user, 'role') and request.user.role else None
            
            if not user_role_name:
                return Response({
                    'status': 'error',
                    'message': 'User role not found'
                }, status=status.HTTP_403_FORBIDDEN)

            role = None
            commissioner_roles = ['level_1', 'level_2', 'level_3', 'level_4', 'level_5', 'Site-Admin', 'site_admin', 'commissioner', 'Commissioner']
            
            if user_role_name in commissioner_roles:
                role = 'commissioner'
            elif user_role_name in ['permit-section', 'Permit-Section', 'Permit Section']:
                role = 'permit-section'
            elif user_role_name in ['licensee', 'Licensee']:
                role = 'licensee'
            
            if not role:
                 return Response({
                    'status': 'error',
                    'message': f'Unauthorized role: {user_role_name}'
                }, status=status.HTTP_403_FORBIDDEN)

            # Determine User Role
            user_role_name = request.user.role.name if hasattr(request.user, 'role') and request.user.role else None
            
            if not user_role_name:
                return Response({'status': 'error', 'message': 'User role not found'}, status=status.HTTP_403_FORBIDDEN)

            # --- Use WorkflowService to advance stage ---
            from auth.workflow.services import WorkflowService
            from auth.workflow.models import WorkflowStage
            
            # Ensure current_stage is set (if missing for some reason)
            if not requisition.current_stage:
                 try:
                     current_stage = WorkflowStage.objects.get(workflow__name='Supply Chain', name=requisition.status)
                     requisition.current_stage = current_stage
                     requisition.save()
                 except WorkflowStage.DoesNotExist:
                     return Response({'status': 'error', 'message': f'Current stage undefined and could not be inferred from status {requisition.status}'}, status=400)
            
            # Context for validation (if rules use condition)
            context = {
                "role": role,  # role determined above
                "action": action
            }

            # WorkflowService.advance_stage expects:
            # - application
            # - user
            # - target_stage (We need to find this first via validate_transition logic or just find it ourselves)
            
            # Actually, WorkflowService.advance_stage takes `target_stage`. We need to determine which stage is next.
            # WorkflowService.get_next_stages(application) returns generic transitions.
            # We filter for the one matching our role/action.
            
            transitions = WorkflowService.get_next_stages(requisition)
            target_transition = None
            
            for t in transitions:
                cond = t.condition or {}
                # Match logic: condition role/action must match request
                if cond.get('role') == role and cond.get('action') == action:
                    target_transition = t
                    break
            
            if not target_transition:
                return Response({
                    'status': 'error',
                    'message': f'No valid transition for Action: {action} on Stage: {requisition.current_stage.name} for Role: {role}'
                }, status=status.HTTP_400_BAD_REQUEST)
                
            try:
                WorkflowService.advance_stage(
                    application=requisition,
                    user=request.user,
                    target_stage=target_transition.to_stage,
                    context=context, # Context might be used for extra validation in service
                    remarks=f"Action: {action}"
                )
                
                # Sync back to status/status_code for legacy
                # from models.masters.supply_chain.status_master.models import StatusMaster # Removed
                new_stage_name = target_transition.to_stage.name
                requisition.status = new_stage_name
                
                # status_obj = StatusMaster.objects.filter(status_name=new_stage_name).first() # Removed
                # if status_obj:
                #     requisition.status_code = status_obj.status_code
                
                requisition.save() # status update
                
                # Return updated requisition
                serializer = EnaRequisitionDetailSerializer(requisition)
                return Response({
                    'status': 'success',
                    'message': f'Requisition status updated to {new_stage_name}',
                    'data': serializer.data
                }, status=status.HTTP_200_OK)

            except Exception as e:
                 return Response({
                    'status': 'error',
                    'message': str(e)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except EnaRequisitionDetail.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Requisition not found'
            }, status=status.HTTP_404_NOT_FOUND)
            
        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



