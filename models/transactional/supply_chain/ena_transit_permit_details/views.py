from rest_framework import status, views, generics
from rest_framework.response import Response
from django.utils import timezone
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
            
            # Check for stock deduction trigger
            if action == 'PAY':
                # CRITICAL: Handle Wallet Deduction BEFORE status update or stock deduction
                # If wallet deduction fails (insufficient funds), we should NOT proceed.
                self._handle_wallet_deduction(request.user, permit)
                
                # If wallet deduction successful, proceed to stock logic checks
                self._handle_stock_deduction(permit)
            
            serializer = EnaTransitPermitDetailSerializer(permit)
            return Response({
                'status': 'success',
                'message': f'Transit Permit status updated to {new_stage_name}',
                'data': serializer.data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"DEBUG Error Generic: {str(e)}")
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _handle_stock_deduction(self, permit):
        """
        Check if all items in the bill are paid, and if so, deduct stock from BrandWarehouse
        """
        try:
            # 1. Check if ALL items for this bill are paid
            bill_items = EnaTransitPermitDetail.objects.filter(bill_no=permit.bill_no)
            
            # defined paid status - simplistic check based on what we just set
            # Ideally use a list of "paid" statuses if workflow is complex
            # For now, we assume if we just set it to a "PaymentSuccessful..." status, others should match or be in advanced stages
            
            # Count items that are NOT in a paid/approved state
            # "Ready for Payment" is the state BEFORE payment. 
            unpaid_count = bill_items.exclude(
                status__in=[
                    'PaymentSuccessfulandForwardedToOfficerincharge', 
                    'TransitPermitSucessfulyApproved',
                    # Add other post-payment statuses if any
                ]
            ).count()
            
            print(f"DEBUG Stock Deduction: Bill {permit.bill_no} has {unpaid_count} unpaid items")

            if unpaid_count == 0:
                print(f"DEBUG Stock Deduction: All items paid for {permit.bill_no}. Proceeding to deduct stock.")
                # ALL items are paid. Trigger deduction for each.
                
                from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouse, BrandWarehouseUtilization, BrandWarehouseArrival
                
                for item in bill_items:
                    # Check if utilization already exists to prevent double deduction
                    if BrandWarehouseUtilization.objects.filter(permit_no=item.bill_no, brand_warehouse__brand_details=item.brand, brand_warehouse__capacity_size=item.size_ml).exists():
                         print(f"DEBUG: Utilization already exists for {item.brand} {item.size_ml} in bill {item.bill_no}")
                         continue

                    # Find matching BrandWarehouse entry
                    # Match by Brand Name and Size
                    # Note: Fuzzy matching might be needed if names aren't exact, but for now we try exact or icontains
                    warehouse_entry = BrandWarehouse.objects.filter(
                        brand_details__iexact=item.brand, # Assuming brand name matches brand_details
                        capacity_size=int(item.size_ml)
                    ).first()
                    
                    if not warehouse_entry:
                        # Try searching purely by brand name if exact match fails
                        warehouse_entry = BrandWarehouse.objects.filter(
                            brand_details__icontains=item.brand,
                            capacity_size=int(item.size_ml)
                        ).first()
                        
                    if warehouse_entry:
                        print(f"DEBUG: Found warehouse entry {warehouse_entry} for {item.brand}")
                        
                        # Calculate quantity (pieces)
                        # We have item.cases. Need to convert to bottles/pieces if we store pieces in warehouse
                        # BrandWarehouse.current_stock is in UNTIS (pieces/bottles)
                        # We need bottles per case.
                        
                        # Get bottles per case from Master Table (BrandMlInCases)
                        from models.masters.supply_chain.transit_permit.models import BrandMlInCases
                        
                        bottles_per_case = 12 # Default fallback
                        
                        # Try to find specific configuration for this size
                        ml_config = BrandMlInCases.objects.filter(ml=int(warehouse_entry.capacity_size)).first()
                        if ml_config:
                            bottles_per_case = ml_config.pieces_in_case
                            print(f"DEBUG: Found ML configuration for {warehouse_entry.capacity_size}ml: {bottles_per_case} pieces/case")
                        else:
                            print(f"WARNING: No ML configuration found for {warehouse_entry.capacity_size}ml. Using default {bottles_per_case}.")
                            
                            # Fallback logic if needed (optional, but keeping previous hardcoded values as last resort fallback is valid)
                            if warehouse_entry.capacity_size == 750: bottles_per_case = 12
                            elif warehouse_entry.capacity_size == 375: bottles_per_case = 24
                            elif warehouse_entry.capacity_size == 180: bottles_per_case = 48
                            elif warehouse_entry.capacity_size == 650: bottles_per_case = 12
                        
                        total_pieces = int(item.cases) * bottles_per_case
                        
                        # Create Utilization Record
                        # This auto-deducts from BrandWarehouse via the save() method in BrandWarehouseUtilization model
                        utilization = BrandWarehouseUtilization.objects.create(
                            brand_warehouse=warehouse_entry,
                            permit_no=item.bill_no,
                            date=item.date, # Date of permit
                            distributor=item.sole_distributor_name,
                            depot_address=item.depot_address,
                            vehicle=item.vehicle_number,
                            quantity=total_pieces, # Quantity in pieces
                            cases=item.cases,
                            bottles_per_case=bottles_per_case,
                            status='APPROVED', # Setting directly to APPROVED to trigger deduction
                            approved_by='System (Payment Auto-Deduction)',
                            approval_date=timezone.now()
                        )
                        print(f"DEBUG: Created utilization {utilization.id}, deducted {total_pieces} pieces")
                        
                    else:
                        print(f"WARNING: No warehouse entry found for Brand: {item.brand}, Size: {item.size_ml}")
                        
            else:
                print(f"DEBUG: Not deducting stock yet. {unpaid_count} items remaining unpaid.")

        except Exception as e:
            print(f"ERROR inside _handle_stock_deduction: {str(e)}")
            import traceback
            traceback.print_exc()




    def _handle_wallet_deduction(self, user, permit):
        """
        Deduct the permit's financial amounts from the user's wallet.
        Raises exception if insufficient funds.
        """
        try:
            from .models import Wallet, WalletTransaction
            
            # 1. Get Wallet
            wallet = Wallet.objects.filter(user=user).first()
            if not wallet:
                print(f"DEBUG: Wallet not found for user {user.username}. Creating default wallet (for dev/sim).")
                wallet = Wallet.objects.create(
                    user=user,
                    excise_balance=10000000.00, # Default high balance for dev
                    additional_excise_balance=10000000.00,
                    education_cess_balance=10000000.00
                )
            
            # 2. Calculate Amounts for THIS permit item
            # Using float conversion to be safe, though Decimal is better
            excise_amount = float(permit.total_excise_duty or 0)
            additional_excise_amount = float(permit.total_additional_excise or 0)
            cess_amount = float(permit.total_education_cess or 0)
            
            total_required_excise = excise_amount
            total_required_additional = additional_excise_amount
            total_required_cess = cess_amount
            
            print(f"DEBUG Wallet Deduction: Excise: {excise_amount}, Add.Excise: {additional_excise_amount}, Cess: {cess_amount}")
            
            # 3. Check Balances
            if float(wallet.excise_balance) < total_required_excise:
                raise Exception(f"Insufficient Excise Wallet Balance. Available: {wallet.excise_balance}, Required: {total_required_excise}")
            
            if float(wallet.additional_excise_balance) < total_required_additional:
                 raise Exception(f"Insufficient Additional Excise Wallet Balance. Available: {wallet.additional_excise_balance}, Required: {total_required_additional}")
                 
            if float(wallet.education_cess_balance) < total_required_cess:
                raise Exception(f"Insufficient Education Cess Wallet Balance. Available: {wallet.education_cess_balance}, Required: {total_required_cess}")
                
            # 4. Deduct
            wallet.excise_balance = float(wallet.excise_balance) - total_required_excise
            wallet.additional_excise_balance = float(wallet.additional_excise_balance) - total_required_additional
            wallet.education_cess_balance = float(wallet.education_cess_balance) - total_required_cess
            wallet.save()
            
            # 5. Log Transactions
            if total_required_excise > 0:
                WalletTransaction.objects.create(
                    wallet=wallet, transaction_type='DEBIT', amount=total_required_excise, 
                    head='EXCISE', reference_no=permit.bill_no, description=f'Payment for Permit Item {permit.id}'
                )
            if total_required_additional > 0:
                WalletTransaction.objects.create(
                    wallet=wallet, transaction_type='DEBIT', amount=total_required_additional, 
                    head='ADDITIONAL_EXCISE', reference_no=permit.bill_no, description=f'Payment for Permit Item {permit.id}'
                )
            if total_required_cess > 0:
                WalletTransaction.objects.create(
                    wallet=wallet, transaction_type='DEBIT', amount=total_required_cess, 
                    head='EDUCATION_CESS', reference_no=permit.bill_no, description=f'Payment for Permit Item {permit.id}'
                )
                
            print(f"DEBUG: Wallet deduction successful. New Balances - Excise: {wallet.excise_balance}, Cess: {wallet.education_cess_balance}")

        except Exception as e:
            print(f"ERROR: Wallet Deduction Failed: {e}")
            raise e # Re-raise to stop the transaction/response
