from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from .models import EnaRevalidationDetail
from .serializers import EnaRevalidationDetailSerializer
# from models.masters.supply_chain.status_master.models import StatusMaster, WorkflowRule # Removed

class EnaRevalidationDetailViewSet(viewsets.ModelViewSet):
    queryset = EnaRevalidationDetail.objects.all().order_by('-created_at')
    serializer_class = EnaRevalidationDetailSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        queryset = EnaRevalidationDetail.objects.all().order_by('-created_at')
        try:
            if hasattr(self.request.user, 'supply_chain_profile'):
                 profile = self.request.user.supply_chain_profile
                 queryset = queryset.filter(licensee_id=profile.licensee_id)
        except Exception:
            pass
        return queryset

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
            
            # Use Workflow Logic for initialization
            from auth.workflow.models import Workflow, WorkflowStage
            
            # HARDCODED INITIAL STATE (StatusMaster module is deprecated/removed)
            status_name = 'ForwardedRevalidationToCommissioner'
            status_code = 'RV_02' # Assuming 01 was Pending, 02 might be Forwarded - this is just a string code
            
            # Sync to fields
            revalidation.status = status_name
            revalidation.status_code = status_code
            
            # Bind to Workflow
            try:
                workflow = Workflow.objects.get(name='ENA Revalidation')
                stage = WorkflowStage.objects.get(workflow=workflow, name=status_name)
                
                revalidation.workflow = workflow
                revalidation.current_stage = stage
            except Exception as e:
                # Log warning but don't fail if workflow setup incomplete (though it should be complete)
                print(f"Warning: Workflow binding failed: {e}")

            revalidation.save()
            
            serializer = self.get_serializer(revalidation)
            return Response({
                'status': 'success',
                'message': f'Revalidation submitted with status: {status_name}',
                'data': serializer.data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def perform_action(self, request, pk=None):
        """Perform an action (APPROVE/REJECT) on a revalidation using WorkflowService"""
        try:
            revalidation = self.get_object()
            action_type = request.data.get('action') # APPROVE / REJECT
            remarks = request.data.get('remarks', f"Action {action_type} performed")
            
            if not action_type:
                 return Response({'error': 'Action is required'}, status=status.HTTP_400_BAD_REQUEST)

            # Determine Role
            user = request.user
            user_role_name = user.role.name if hasattr(user, 'role') and user.role else None
            role = user_role_name # Simple pass-through or use mapping if needed
            
            # Use Mapping (Consistent with Requisition)
            role_mapped = None
            commissioner_roles = ['level_1', 'level_2', 'level_3', 'level_4', 'level_5', 'Site-Admin', 'site_admin', 'commissioner', 'Commissioner']
            
            if user_role_name in commissioner_roles:
                role_mapped = 'commissioner'
            elif user_role_name in ['permit-section', 'Permit-Section', 'Permit Section']:
                role_mapped = 'permit-section'
            elif user_role_name in ['licensee', 'Licensee']:
                role_mapped = 'licensee'
            else:
                role_mapped = user_role_name # Fallback

            # Use Workflow Service
            from auth.workflow.services import WorkflowService
            
            # Ensure workflow/stage is set (migration fallback)
            if not revalidation.workflow or not revalidation.current_stage:
                 # Try to recover state from status_name
                 from auth.workflow.models import Workflow, WorkflowStage
                 try:
                     wf = Workflow.objects.get(name='ENA Revalidation')
                     stage = WorkflowStage.objects.get(workflow=wf, name=revalidation.status)
                     revalidation.workflow = wf
                     revalidation.current_stage = stage
                     revalidation.save()
                 except Exception as e:
                     return Response({'error': f'Workflow state error: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # Find Transition
            transitions = WorkflowService.get_next_stages(revalidation)
            target_transition = None
            
            for t in transitions:
                cond = t.condition or {}
                # Match Logic
                if cond.get('role') == role_mapped and cond.get('action') == action_type:
                    target_transition = t
                    break
            
            if not target_transition:
                return Response({
                    'error': f'Invalid action {action_type} for role {role_mapped} at stage {revalidation.current_stage.name}'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Advance Stage
            try:
                WorkflowService.advance_stage(
                    application=revalidation,
                    user=user,
                    target_stage=target_transition.to_stage,
                    context={'role': role_mapped, 'action': action_type},
                    remarks=remarks
                )
                
                # Update status explicitly
                revalidation.status = target_transition.to_stage.name
                # revalidation.status_code = ... # Removed dependency
                revalidation.save()

                serializer = self.get_serializer(revalidation)
                return Response({
                    'status': 'success',
                    'message': f'Action {action_type} performed successfully. New Status: {revalidation.status}',
                    'data': serializer.data
                }, status=status.HTTP_200_OK)

            except ValueError as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
            except PermissionError as e:
                return Response({'error': str(e)}, status=status.HTTP_403_FORBIDDEN)
            
        except EnaRevalidationDetail.DoesNotExist:
            return Response({
                'error': 'Revalidation not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
