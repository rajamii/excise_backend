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
            from models.masters.supply_chain.status_master.models import StatusMaster, WorkflowRule
            
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

            # Find the rule in the database
            try:
                rule = WorkflowRule.objects.get(
                    current_status__status_code=current_status_code,
                    action=action,
                    allowed_role=role
                )
                new_status = rule.next_status
                
            except WorkflowRule.DoesNotExist:
                return Response({
                    'status': 'error',
                    'message': f'No workflow rule defined for Action: {action} on Status: {requisition.status} ({current_status_code}) for Role: {role}'
                }, status=status.HTTP_400_BAD_REQUEST)
            except WorkflowRule.MultipleObjectsReturned:
                 return Response({
                    'status': 'error',
                    'message': f'Multiple workflow rules found. Configuration error.'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # Update the requisition status
            requisition.status = new_status.status_name
            requisition.status_code = new_status.status_code
            requisition.save()
            
            # Return updated requisition
            serializer = EnaRequisitionDetailSerializer(requisition)
            
            return Response({
                'status': 'success',
                'message': f'Requisition status updated to {new_status.status_name}',
                'data': serializer.data
            }, status=status.HTTP_200_OK)
            
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



