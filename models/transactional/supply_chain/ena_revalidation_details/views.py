from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from .models import EnaRevalidationDetail
from .serializers import EnaRevalidationDetailSerializer
from models.masters.supply_chain.status_master.models import StatusMaster, WorkflowRule

class EnaRevalidationDetailViewSet(viewsets.ModelViewSet):
    queryset = EnaRevalidationDetail.objects.all().order_by('-created_at')
    serializer_class = EnaRevalidationDetailSerializer
    permission_classes = [AllowAny]

    def get_serializer_context(self):
        """Override to ensure request context is passed to serializer"""
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    # Note: allowed_actions is now handled by SerializerMethodField in serializer
    # Following the same pattern as requisition - no custom list() override needed

    @action(detail=True, methods=['post'])
    def submit_revalidation(self, request, pk=None):
        """Submit a revalidation request and set initial status"""
        try:
            revalidation = self.get_object()
            
            # Set status to RevalidationPending (RV_00)
            status_obj = StatusMaster.objects.get(status_code='RV_00')
            revalidation.status = status_obj.status_name
            revalidation.status_code = status_obj.status_code
            revalidation.save()
            
            serializer = self.get_serializer(revalidation)
            return Response({
                'status': 'success',
                'message': f'Revalidation submitted with status: {status_obj.status_name}',
                'data': serializer.data
            }, status=status.HTTP_200_OK)
            
        except StatusMaster.DoesNotExist:
            return Response({
                'error': 'Status RV_00 (RevalidationPending) not found'
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def perform_action(self, request, pk=None):
        """Perform an action (APPROVE/REJECT) on a revalidation"""
        try:
            revalidation = self.get_object()
            action_type = request.data.get('action')
            role = request.data.get('role')
            
            if not action_type or action_type not in ['APPROVE', 'REJECT']:
                return Response({
                    'error': 'Valid action (APPROVE or REJECT) is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if not role:
                return Response({
                    'error': 'Role is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Get current status code lookup first, fallback to name
            current_status = None
            if revalidation.status_code:
                 current_status = StatusMaster.objects.filter(status_code=revalidation.status_code).first()
            
            if not current_status:
                current_status = StatusMaster.objects.filter(status_name=revalidation.status).first()
                
            if not current_status:
                return Response({
                    'error': f'Current status {revalidation.status} not found in status master'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Find workflow rule
            try:
                rule = WorkflowRule.objects.get(
                    current_status=current_status,
                    action=action_type,
                    allowed_role=role
                )
                new_status = rule.next_status
                
            except WorkflowRule.DoesNotExist:
                return Response({
                    'error': f'No workflow rule for {action_type} on status {revalidation.status} for role {role}'
                }, status=status.HTTP_400_BAD_REQUEST)
            except WorkflowRule.MultipleObjectsReturned:
                # Handle duplicate rules gracefully (e.g. if my populate script duplicated entries)
                rule = WorkflowRule.objects.filter(
                    current_status=current_status,
                    action=action_type,
                    allowed_role=role
                ).first()
                new_status = rule.next_status
            
            # Update status
            revalidation.status = new_status.status_name
            revalidation.status_code = new_status.status_code
            revalidation.save()
            
            serializer = self.get_serializer(revalidation)
            return Response({
                'status': 'success',
                'message': f'Revalidation status updated to {new_status.status_name}',
                'data': serializer.data
            }, status=status.HTTP_200_OK)
            
        except EnaRevalidationDetail.DoesNotExist:
            return Response({
                'error': 'Revalidation not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
