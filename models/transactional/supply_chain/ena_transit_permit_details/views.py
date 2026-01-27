from rest_framework import status, views, generics
from rest_framework.response import Response
from .serializers import TransitPermitSubmissionSerializer, EnaTransitPermitDetailSerializer
from .models import EnaTransitPermitDetail


class SubmitTransitPermitAPIView(views.APIView):
    def post(self, request):
        print(f"DEBUG: Raw Request Data keys: {list(request.data.keys())}")
        print(f"DEBUG: Full Request Data: {request.data}")
        serializer = TransitPermitSubmissionSerializer(data=request.data)
        if serializer.is_valid():
            data = serializer.validated_data
            bill_no = data['bill_no']
            
            # 1. Uniqueness Check (Application Level)
            if EnaTransitPermitDetail.objects.filter(bill_no=bill_no).exists():
                return Response({
                    "status": "error",
                    "message": "Submission failed. Bill Number already exists."
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # 2. Prepare common data
            sole_distributor_name = data['sole_distributor']
            date = data['date']
            depot_address = data['depot_address']
            vehicle_number = data['vehicle_number']
            products = data['products'] 
            
            # Determine Licensee ID
            licensee_id = None
            if hasattr(request.user, 'supply_chain_profile'):
                licensee_id = request.user.supply_chain_profile.licensee_id
            
            created_records = []
            
            # 3. Save each product as a new row
            try:
                for product in products:
                    obj = EnaTransitPermitDetail(
                        bill_no=bill_no,
                        sole_distributor_name=sole_distributor_name,
                        date=date,
                        depot_address=depot_address,
                        vehicle_number=vehicle_number,
                        licensee_id=licensee_id,
                        
                        brand=product.get('brand'),
                        size_ml=product.get('size'), 
                        cases=product.get('cases'),
                        bottle_type=product.get('bottle_type', ''), # Save bottle_type

                        # New fields
                        brand_owner=product.get('brand_owner', ''),
                        liquor_type=product.get('liquor_type', ''),
                        exfactory_price_rs_per_case=product.get('ex_factory_price', 0.00),
                        
                        excise_duty_rs_per_case=product.get('excise_duty', 0.00),
                        education_cess_rs_per_case=product.get('education_cess', 0.00),
                        additional_excise_duty_rs_per_case=product.get('additional_excise', 0.00),
                        
                        manufacturing_unit_name=product.get('manufacturing_unit_name', ''),

                        # Calculated totals
                        total_excise_duty=float(product.get('excise_duty', 0.00)) * int(product.get('cases', 0)),
                        total_education_cess=float(product.get('education_cess', 0.00)) * int(product.get('cases', 0)),
                        total_additional_excise=float(product.get('additional_excise', 0.00)) * int(product.get('cases', 0)),
                        total_amount=(
                            (float(product.get('excise_duty', 0.00)) + 
                             float(product.get('education_cess', 0.00)) + 
                             float(product.get('additional_excise', 0.00))) * int(product.get('cases', 0))
                        )
                    )

                    # Initial Status Assignment
                    obj.status = 'Ready for Payment'
                    obj.status_code = 'TRP_01'
                    
                    # Optional: specific stage lookup
                    # from auth.workflow.models import WorkflowStage
                    # stage = WorkflowStage.objects.filter(workflow__name='Transit Permit', name='Ready for Payment').first()
                    # if stage:
                    #     obj.current_stage = stage

                    obj.save()
                    created_records.append(obj)
                
                return Response({
                    "status": "success",
                    "message": "Transit Permit Submitted Successfully",
                    "count": len(created_records)
                }, status=status.HTTP_201_CREATED)
                
            except Exception as e:
                 return Response({
                    "status": "error",
                    "message": str(e)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        print(f"Validation Errors: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class GetTransitPermitAPIView(generics.ListAPIView):
    serializer_class = EnaTransitPermitDetailSerializer

    def get_queryset(self):
        queryset = EnaTransitPermitDetail.objects.all().order_by('-id') # Order by newest first
        bill_no = self.request.query_params.get('bill_no')
        if bill_no:
            queryset = queryset.filter(bill_no=bill_no)
        return queryset


class PerformTransitPermitActionAPIView(views.APIView):
    """
    API endpoint to perform an action (PAY, APPROVE, REJECT) on a transit permit.
    Dynamically determines the next status based on the current status and the action
    by querying the WorkflowTransition table.
    """
    def post(self, request, pk):
        try:
            action = request.data.get('action')
            if not action or action not in ['PAY', 'APPROVE', 'REJECT']:
                return Response({
                    'status': 'error',
                    'message': 'Valid action (PAY, APPROVE, or REJECT) is required'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Get the transit permit
            permit = EnaTransitPermitDetail.objects.get(pk=pk)
            
            # Determine User Role
            # Simplified logic: In real app, check request.user.role.name
            role = 'licensee' # default to licensee for PAY
            if action in ['APPROVE', 'REJECT']:
                 role = 'officer' # default to officer actions

            # --- Use WorkflowService to advance stage ---
            from auth.workflow.services import WorkflowService
            from auth.workflow.models import WorkflowStage
            
            # Ensure current_stage is set (if missing)
            if not permit.current_stage or not permit.workflow:
                 try:
                     # Try to find by name if stage ID missing
                     from auth.workflow.models import Workflow
                     workflow_obj = Workflow.objects.get(name='Transit Permit')
                     permit.workflow = workflow_obj
                     
                     current_stage = WorkflowStage.objects.get(workflow=workflow_obj, name=permit.status)
                     permit.current_stage = current_stage
                     permit.save()
                 except (Workflow.DoesNotExist, WorkflowStage.DoesNotExist):
                     return Response({
                        'status': 'error',
                        'message': 'Workflow configuration not found. Please run "python manage.py populate_transit_permit_workflow".'
                     }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                 except Exception as e:
                     return Response({
                        'status': 'error',
                        'message': f"Database Error during workflow initialization: {str(e)}"
                     }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Extra check to be sure
            if not permit.current_stage:
                 return Response({
                    'status': 'error',
                    'message': 'Current Stage is Null. Workflow initialization failed.'
                 }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Context for validation
            context = {
                "role": role,
                "action": action
            }

            transitions = WorkflowService.get_next_stages(permit)
            target_transition = None
            
            for t in transitions:
                cond = t.condition or {}
                # Match logic: condition role/action must match request context (or be loose)
                # For this implementation, we check if the action matches. Role check optional or manual.
                if cond.get('action') == action: # Strict role check: and cond.get('role') == role:
                    target_transition = t
                    break
            
            if not target_transition:
                return Response({
                    'status': 'error',
                    'message': f'No valid transition for Action: {action} on Status: {permit.status}'
                }, status=status.HTTP_400_BAD_REQUEST)
                
            WorkflowService.advance_stage(
                application=permit,
                user=request.user,
                target_stage=target_transition.to_stage,
                context=context,
                remarks=f"Action: {action}"
            )
            
            # Sync back to status/status_code
            new_stage_name = target_transition.to_stage.name
            permit.status = new_stage_name
            # Update status code based on name map (simplified)
            if new_stage_name == 'Ready for Payment': permit.status_code = 'TRP_01'
            elif new_stage_name == 'PaymentSuccessfulandForwardedToOfficerincharge': permit.status_code = 'TRP_02'
            elif new_stage_name == 'TransitPermitSucessfulyApproved': permit.status_code = 'TRP_03'
            elif new_stage_name == 'Cancelled by Officer In-Charge - Refund Initiated Successfully': permit.status_code = 'TRP_04'
            
            permit.save()
            
            serializer = EnaTransitPermitDetailSerializer(permit)
            return Response({
                'status': 'success',
                'message': f'Transit Permit status updated to {new_stage_name}',
                'data': serializer.data
            }, status=status.HTTP_200_OK)

        except EnaTransitPermitDetail.DoesNotExist:
            print(f"DEBUG Error: Transit Permit {pk} not found")
            return Response({
                'status': 'error',
                'message': 'Transit Permit not found'
            }, status=status.HTTP_404_NOT_FOUND)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"DEBUG Error Generic: {str(e)}")
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

