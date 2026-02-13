from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
import re
from .models import EnaRequisitionDetail
from .serializers import EnaRequisitionDetailSerializer
from auth.workflow.constants import WORKFLOW_IDS
from models.transactional.supply_chain.access_control import (
    has_workflow_access,
    scope_by_profile_or_workflow,
    transition_matches,
)


class EnaRequisitionDetailListCreateAPIView(generics.ListCreateAPIView):
    queryset = EnaRequisitionDetail.objects.all()
    serializer_class = EnaRequisitionDetailSerializer

    def get_queryset(self):
        queryset = EnaRequisitionDetail.objects.all()
        queryset = scope_by_profile_or_workflow(
            self.request.user,
            queryset,
            WORKFLOW_IDS['ENA_REQUISITION'],
            licensee_field='licensee_id'
        )

        our_ref_no = self.request.query_params.get('our_ref_no', None)
        if our_ref_no is not None:
            queryset = queryset.filter(our_ref_no=our_ref_no)
        return queryset


class EnaRequisitionDetailRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = EnaRequisitionDetailSerializer

    def get_queryset(self):
        queryset = EnaRequisitionDetail.objects.all()
        queryset = scope_by_profile_or_workflow(
            self.request.user,
            queryset,
            WORKFLOW_IDS['ENA_REQUISITION'],
            licensee_field='licensee_id'
        )
        return queryset


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

            # Licensee users can only act on their own requisitions.
            if hasattr(request.user, 'supply_chain_profile'):
                user_licensee_id = request.user.supply_chain_profile.licensee_id
                if str(requisition.licensee_id) != str(user_licensee_id):
                    raise PermissionDenied("You are not allowed to modify this requisition.")
            if not has_workflow_access(request.user, WORKFLOW_IDS['ENA_REQUISITION']) and not hasattr(request.user, 'supply_chain_profile'):
                return Response({
                    'status': 'error',
                    'message': 'Unauthorized role for this workflow'
                }, status=status.HTTP_403_FORBIDDEN)

            # --- Use WorkflowService to advance stage ---
            from auth.workflow.services import WorkflowService
            from auth.workflow.models import WorkflowStage
            
            # Ensure current_stage is set (if missing for some reason)
            if not requisition.current_stage:
                 try:
                     if requisition.workflow_id:
                         current_stage = WorkflowStage.objects.get(workflow_id=requisition.workflow_id, name=requisition.status)
                     else:
                         current_stage = WorkflowStage.objects.get(
                             workflow_id=WORKFLOW_IDS['ENA_REQUISITION'],
                             name=requisition.status
                         )
                     requisition.current_stage = current_stage
                     requisition.save()
                 except WorkflowStage.DoesNotExist:
                     return Response({'status': 'error', 'message': f'Current stage undefined and could not be inferred from status {requisition.status}'}, status=400)
            
            # Context for validation (if rules use condition)
            context = {
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
                if transition_matches(t, request.user, action):
                    target_transition = t
                    break
            
            if not target_transition:
                return Response({
                    'status': 'error',
                    'message': f'No valid transition for Action: {action} on Stage: {requisition.current_stage.name}'
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



