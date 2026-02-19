from rest_framework import status, views, generics
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from decimal import Decimal
import re
from .serializers import TransitPermitSubmissionSerializer, EnaTransitPermitDetailSerializer
from .models import EnaTransitPermitDetail
from auth.workflow.constants import WORKFLOW_IDS
from models.transactional.supply_chain.access_control import (
    has_workflow_access,
    scope_by_profile_or_workflow,
    transition_matches,
)


class SubmitTransitPermitAPIView(views.APIView):
    permission_classes = [IsAuthenticated]

    def _generate_transit_ref(self) -> str:
        existing_refs = EnaTransitPermitDetail.objects.values_list('bill_no', flat=True)
        pattern = r'TRN/(\d+)/EXCISE'
        numbers = []

        for ref in existing_refs:
            match = re.match(pattern, str(ref or ''))
            if match:
                numbers.append(int(match.group(1)))

        next_number = (max(numbers) + 1) if numbers else 1
        return f"TRN/{next_number:02d}/EXCISE"

    def _resolve_approved_license_id(self, user) -> str:
        """
        Resolve currently active/approved license id (NA/... preferred) for transit records.
        """
        raw_profile_id = ''
        if hasattr(user, 'supply_chain_profile'):
            raw_profile_id = str(getattr(user.supply_chain_profile, 'licensee_id', '') or '').strip()

        from models.masters.license.models import License

        active_licenses = License.objects.filter(
            applicant=user,
            source_type='new_license_application',
            is_active=True
        ).order_by('-issue_date')

        if raw_profile_id:
            hit = active_licenses.filter(
                Q(license_id=raw_profile_id) | Q(source_object_id=raw_profile_id)
            ).first()
            if hit and hit.license_id:
                return str(hit.license_id).strip()

            if raw_profile_id.startswith('NLI/'):
                na_alias = f"NA/{raw_profile_id[4:]}"
                hit_alias = active_licenses.filter(license_id=na_alias).first()
                if hit_alias and hit_alias.license_id:
                    return str(hit_alias.license_id).strip()

            if raw_profile_id.startswith('NA/'):
                return raw_profile_id

        latest = active_licenses.first()
        if latest and latest.license_id:
            return str(latest.license_id).strip()

        return raw_profile_id

    def _debit_wallet_balances_for_submit(self, user, license_id: str, bill_no: str, permit_rows):
        """
        Debit Excise and Education Cess wallets at submit time and persist wallet transactions.
        Additional excise is debited from excise wallet.
        """
        from models.transactional.payment.models import WalletBalance, WalletTransaction

        license_id = str(license_id or '').strip()
        if not license_id:
            raise ValueError("Unable to resolve approved license id for wallet deduction.")

        excise_total = Decimal("0.00")
        education_total = Decimal("0.00")
        for row in permit_rows:
            excise_total += Decimal(str(row.total_excise_duty or 0)) + Decimal(str(row.total_additional_excise or 0))
            education_total += Decimal(str(row.total_education_cess or 0))

        if excise_total <= 0 and education_total <= 0:
            return

        username = str(getattr(user, 'username', '') or '')

        with transaction.atomic():
            excise_wallet = (
                WalletBalance.objects.select_for_update()
                .filter(licensee_id=license_id, wallet_type__iexact='excise')
                .order_by('wallet_balance_id')
                .first()
            )
            education_wallet = (
                WalletBalance.objects.select_for_update()
                .filter(licensee_id=license_id, wallet_type__iexact='education_cess')
                .order_by('wallet_balance_id')
                .first()
            )

            if excise_total > 0 and not excise_wallet:
                raise ValueError(f"Excise wallet not found for license_id={license_id}")
            if education_total > 0 and not education_wallet:
                raise ValueError(f"Education cess wallet not found for license_id={license_id}")

            if excise_wallet and Decimal(str(excise_wallet.current_balance or 0)) < excise_total:
                raise ValueError(
                    f"Insufficient Excise Wallet Balance. Available: {excise_wallet.current_balance}, Required: {excise_total}"
                )
            if education_wallet and Decimal(str(education_wallet.current_balance or 0)) < education_total:
                raise ValueError(
                    f"Insufficient Education Cess Wallet Balance. Available: {education_wallet.current_balance}, Required: {education_total}"
                )

            now_ts = timezone.now()

            if excise_wallet and excise_total > 0:
                before = Decimal(str(excise_wallet.current_balance or 0))
                after = before - excise_total
                excise_wallet.current_balance = after
                excise_wallet.total_debit = Decimal(str(excise_wallet.total_debit or 0)) + excise_total
                excise_wallet.last_updated_at = now_ts
                excise_wallet.save(update_fields=['current_balance', 'total_debit', 'last_updated_at'])

                WalletTransaction.objects.create(
                    wallet_balance=excise_wallet,
                    transaction_id=f"TRP-{bill_no}-EXCISE",
                    licensee_id=license_id,
                    licensee_name=excise_wallet.licensee_name,
                    user_id=username or excise_wallet.user_id,
                    module_type=excise_wallet.module_type,
                    wallet_type=excise_wallet.wallet_type,
                    head_of_account=excise_wallet.head_of_account,
                    entry_type='DR',
                    transaction_type='debit',
                    amount=excise_total,
                    balance_before=before,
                    balance_after=after,
                    reference_no=bill_no,
                    source_module='transit_permit',
                    payment_status='success',
                    remarks='Transit permit submit debit (excise + additional excise)',
                    created_at=now_ts,
                )

            if education_wallet and education_total > 0:
                before = Decimal(str(education_wallet.current_balance or 0))
                after = before - education_total
                education_wallet.current_balance = after
                education_wallet.total_debit = Decimal(str(education_wallet.total_debit or 0)) + education_total
                education_wallet.last_updated_at = now_ts
                education_wallet.save(update_fields=['current_balance', 'total_debit', 'last_updated_at'])

                WalletTransaction.objects.create(
                    wallet_balance=education_wallet,
                    transaction_id=f"TRP-{bill_no}-EDUCATION",
                    licensee_id=license_id,
                    licensee_name=education_wallet.licensee_name,
                    user_id=username or education_wallet.user_id,
                    module_type=education_wallet.module_type,
                    wallet_type=education_wallet.wallet_type,
                    head_of_account=education_wallet.head_of_account,
                    entry_type='DR',
                    transaction_type='debit',
                    amount=education_total,
                    balance_before=before,
                    balance_after=after,
                    reference_no=bill_no,
                    source_module='transit_permit',
                    payment_status='success',
                    remarks='Transit permit submit debit (education cess)',
                    created_at=now_ts,
                )

    def _create_utilization_and_deduct_stock_for_submit(self, permit_rows, license_id: str):
        """
        Create BrandWarehouseUtilization rows immediately on submit and deduct stock.
        This keeps OIC utilization dashboard in sync without waiting for a separate PAY action.
        """
        from models.transactional.supply_chain.brand_warehouse.models import (
            BrandWarehouse,
            BrandWarehouseUtilization,
        )
        from models.masters.supply_chain.transit_permit.models import BrandMlInCases

        normalized_license_id = str(license_id or '').strip()

        for item in permit_rows:
            item_license_id = str(getattr(item, 'licensee_id', '') or '').strip() or normalized_license_id

            warehouse_qs = BrandWarehouse.objects.filter(
                capacity_size=int(item.size_ml),
            )
            if item_license_id:
                warehouse_qs = warehouse_qs.filter(license_id=item_license_id)

            warehouse_entry = warehouse_qs.filter(brand_details__iexact=item.brand).first()
            if not warehouse_entry:
                warehouse_entry = warehouse_qs.filter(brand_details__icontains=item.brand).first()
            if not warehouse_entry:
                raise ValueError(
                    f"Brand warehouse entry not found for brand={item.brand}, size={item.size_ml}, "
                    f"license_id={item_license_id or 'N/A'}"
                )

            resolved_license_id = item_license_id or str(getattr(warehouse_entry, 'license_id', '') or '').strip()

            utilization_exists = BrandWarehouseUtilization.objects.filter(
                permit_no=item.bill_no,
                brand_warehouse=warehouse_entry,
                distributor=item.sole_distributor_name,
                depot_address=item.depot_address,
                vehicle=item.vehicle_number,
                cases=item.cases,
                quantity=int(item.cases) * int(item.bottles_per_case or 0 or 1),
            ).exists()
            if utilization_exists:
                continue

            bottles_per_case = int(item.bottles_per_case or 0)
            if bottles_per_case <= 0:
                ml_config = BrandMlInCases.objects.filter(ml=int(warehouse_entry.capacity_size)).first()
                bottles_per_case = int(ml_config.pieces_in_case) if ml_config and ml_config.pieces_in_case else 1

            total_pieces = int(item.cases) * bottles_per_case

            BrandWarehouseUtilization.objects.create(
                brand_warehouse=warehouse_entry,
                license_id=resolved_license_id or None,
                permit_no=item.bill_no,
                date=item.date,
                distributor=item.sole_distributor_name,
                depot_address=item.depot_address,
                vehicle=item.vehicle_number,
                quantity=total_pieces,
                cases=item.cases,
                bottles_per_case=bottles_per_case,
                status='APPROVED',
                approved_by='System (Submit Auto-Deduction)',
                approval_date=timezone.now(),
            )

    def post(self, request):
        print(f"DEBUG: Raw Request Data keys: {list(request.data.keys())}")
        print(f"DEBUG: Full Request Data: {request.data}")
        serializer = TransitPermitSubmissionSerializer(data=request.data)
        if serializer.is_valid():
            data = serializer.validated_data
            bill_no = self._generate_transit_ref()
            
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
            
            # Store approved license id in permit rows for profile-scoped dashboards.
            licensee_id = self._resolve_approved_license_id(request.user)
            if not (str(licensee_id).startswith('NA/') or str(licensee_id).startswith('NLI/')):
                return Response({
                    "status": "error",
                    "message": "Approved license id not found for this profile. Please switch to the approved unit/profile first."
                }, status=status.HTTP_400_BAD_REQUEST)
            
            created_records = []
            
            # 3. Save each product as a new row
            try:
                with transaction.atomic():
                    workflow_obj = None
                    paid_stage = None
                    try:
                        from auth.workflow.models import Workflow, WorkflowStage
                        workflow_obj = Workflow.objects.filter(id=WORKFLOW_IDS['TRANSIT_PERMIT']).first()
                        if workflow_obj:
                            paid_stage = WorkflowStage.objects.filter(
                                workflow=workflow_obj,
                                name='PaymentSuccessfulandForwardedToOfficerincharge'
                            ).first()
                    except Exception:
                        workflow_obj = None
                        paid_stage = None

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
                            
                            # Save Historical Bottles Per Case
                            bottles_per_case=self._get_bottles_per_case(product.get('size'), product.get('brand')),
                            
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

                        # Payment is completed on submit; forward directly to OIC stage.
                        obj.status = 'PaymentSuccessfulandForwardedToOfficerincharge'
                        obj.status_code = 'TRP_02'
                        if workflow_obj:
                            obj.workflow = workflow_obj
                        if paid_stage:
                            obj.current_stage = paid_stage
                        obj.save()
                        created_records.append(obj)

                    # Deduct wallet immediately on submit from excise + education wallets.
                    self._debit_wallet_balances_for_submit(
                        user=request.user,
                        license_id=licensee_id,
                        bill_no=bill_no,
                        permit_rows=created_records
                    )

                    # Create utilization entries and deduct warehouse stock immediately.
                    self._create_utilization_and_deduct_stock_for_submit(
                        permit_rows=created_records,
                        license_id=licensee_id,
                    )
                
                return Response({
                    "status": "success",
                    "message": "Transit Permit submitted, payment deducted, and forwarded to Officer In-Charge.",
                    "count": len(created_records)
                }, status=status.HTTP_201_CREATED)
                
            except ValueError as e:
                 return Response({
                    "status": "error",
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                 return Response({
                    "status": "error",
                    "message": str(e)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        print(f"Validation Errors: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def _get_bottles_per_case(self, size_ml, brand_name):
        try:
            from models.masters.supply_chain.transit_permit.models import BrandMlInCases
            # Try to find specific configuration for this size
            if size_ml:
                ml_config = BrandMlInCases.objects.filter(ml=int(size_ml)).first()
                if ml_config:
                    return ml_config.pieces_in_case
        except Exception as e:
            print(f"Error fetching bottles per case: {e}")
        
        # Fallbacks
        try:
            size_ml = int(size_ml)
            if size_ml == 750: return 12
            if size_ml == 375: return 24
            if size_ml == 180: return 48
            if size_ml == 650: return 12
            if size_ml == 90: return 96
        except:
            pass
            
        return 12 # Ultimate default

class GetTransitPermitAPIView(generics.ListAPIView):
    serializer_class = EnaTransitPermitDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = EnaTransitPermitDetail.objects.all().order_by('-id') # Order by newest first

        queryset = scope_by_profile_or_workflow(
            self.request.user,
            queryset,
            WORKFLOW_IDS['TRANSIT_PERMIT'],
            licensee_field='licensee_id'
        )

        bill_no = self.request.query_params.get('bill_no')
        if bill_no:
            queryset = queryset.filter(bill_no=bill_no)
        return queryset

class GetTransitPermitDetailAPIView(generics.RetrieveAPIView):
    serializer_class = EnaTransitPermitDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = EnaTransitPermitDetail.objects.all()
        return scope_by_profile_or_workflow(
            self.request.user,
            queryset,
            WORKFLOW_IDS['TRANSIT_PERMIT'],
            licensee_field='licensee_id'
        )



class PerformTransitPermitActionAPIView(views.APIView):
    """
    API endpoint to perform an action (PAY, APPROVE, REJECT) on a transit permit.
    Dynamically determines the next status based on the current status and the action
    by querying the WorkflowTransition table.
    """
    permission_classes = [IsAuthenticated]

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

            # Ownership/permission check (dynamic, DB-driven).
            # Workflow users (OIC/officers) can process mapped workflow items.
            # Licensee users can process only their own permit.
            if has_workflow_access(request.user, WORKFLOW_IDS['TRANSIT_PERMIT']):
                pass
            elif hasattr(request.user, 'supply_chain_profile'):
                user_licensee_id = str(request.user.supply_chain_profile.licensee_id or '').strip()
                permit_licensee_id = str(permit.licensee_id or '').strip()
                if user_licensee_id != permit_licensee_id:
                    raise PermissionDenied("You are not allowed to modify this transit permit.")
            else:
                raise PermissionDenied("You are not allowed to modify this transit permit.")
            
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
                     workflow_obj = Workflow.objects.get(id=WORKFLOW_IDS['TRANSIT_PERMIT'])
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
                if transition_matches(t, request.user, action):
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
                # Wallet is already debited at submit time.
                # On PAY we only continue stock/workflow processing.
                self._handle_stock_deduction(permit)

            elif action == 'REJECT':
                self._handle_rejection(request, permit)
            
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

    def _handle_rejection(self, request, permit):
        print(f"DEBUG: Handling Rejection for Permit {permit.bill_no}")
        try:
            # 1. Refund Wallet
            from .models import Wallet, WalletTransaction
            
            # Find wallet via licensee_id (assuming user.supply_chain_profile.licensee_id matches)
            wallet = Wallet.objects.filter(user__supply_chain_profile__licensee_id=permit.licensee_id).first()
            
            if wallet:
                # Calculate refund amounts
                excise_amt = float(permit.total_excise_duty or 0)
                add_excise_amt = float(permit.total_additional_excise or 0)
                cess_amt = float(permit.total_education_cess or 0)
                
                # Refund
                wallet.excise_balance = float(wallet.excise_balance) + excise_amt
                wallet.additional_excise_balance = float(wallet.additional_excise_balance) + add_excise_amt
                wallet.education_cess_balance = float(wallet.education_cess_balance) + cess_amt
                wallet.save()
                
                # Log Transactions (CREDIT)
                if excise_amt > 0:
                    WalletTransaction.objects.create(wallet=wallet, transaction_type='CREDIT', amount=excise_amt, head='EXCISE', reference_no=permit.bill_no, description=f'Refund for Rejected Permit {permit.bill_no}')
                if add_excise_amt > 0:
                    WalletTransaction.objects.create(wallet=wallet, transaction_type='CREDIT', amount=add_excise_amt, head='ADDITIONAL_EXCISE', reference_no=permit.bill_no, description=f'Refund for Rejected Permit {permit.bill_no}')
                if cess_amt > 0:
                    WalletTransaction.objects.create(wallet=wallet, transaction_type='CREDIT', amount=cess_amt, head='EDUCATION_CESS', reference_no=permit.bill_no, description=f'Refund for Rejected Permit {permit.bill_no}')
                
                print(f"DEBUG: Wallet refunded for {permit.bill_no}")
            else:
                print(f"WARNING: No wallet found for licensee_id {permit.licensee_id}, skipping refund")

            # 2. Restore Stock & Log Cancellation
            from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouseUtilization, BrandWarehouseTpCancellation
            
            utilizations = BrandWarehouseUtilization.objects.filter(permit_no=permit.bill_no)
            if utilizations.exists():
                for utilization in utilizations:
                    warehouse = utilization.brand_warehouse
                    
                    # Store previous stock
                    previous_stock = warehouse.current_stock
                    
                    # Restore stock
                    warehouse.current_stock += utilization.quantity
                    warehouse.save()
                    warehouse.update_status()
                    
                    # New stock
                    new_stock = warehouse.current_stock
                    
                    # Update Utilization status
                    utilization.status = 'CANCELLED'
                    utilization.save()
                    
                    # Create Cancellation Record
                    BrandWarehouseTpCancellation.objects.create(
                        brand_warehouse=warehouse,
                        reference_no=permit.bill_no,
                        cancelled_by=request.user.username,
                        quantity_cases=utilization.cases,
                        quantity_bottles=utilization.total_bottles,
                        amount_refunded=permit.total_amount, # potentially split this per item if needed, but per permit is okay if fields align
                        reason=request.data.get('remarks', 'Rejected by OIC'),
                        
                        # Stock Snapshots
                        previous_stock=previous_stock,
                        new_stock=new_stock,
                        
                        # New fields
                        permit_date=utilization.date,
                        destination=utilization.distributor, # Using distributor as destination/customer name
                        vehicle_no=utilization.vehicle,
                        depot_address=utilization.depot_address,
                        brand_name=f"{warehouse.brand_type} ({warehouse.capacity_size}ml)" # Construct brand name
                    )
                print(f"DEBUG: Stock restored and cancellation records created for all items in {permit.bill_no}")
            else:
                print(f"WARNING: No utilization found for {permit.bill_no}")


        except Exception as e:
            print(f"ERROR Handling Rejection: {e}")
            # Consider raising if critical
            pass

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
                
                from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouse, BrandWarehouseUtilization
                
                for item in bill_items:
                    item_license_id = str(item.licensee_id or '').strip()

                    # Check if utilization already exists to prevent double deduction
                    utilization_qs = BrandWarehouseUtilization.objects.filter(
                        permit_no=item.bill_no,
                        brand_warehouse__brand_details__iexact=item.brand,
                        brand_warehouse__capacity_size=item.size_ml
                    )
                    if item_license_id:
                        utilization_qs = utilization_qs.filter(brand_warehouse__license_id=item_license_id)
                    if utilization_qs.exists():
                         print(f"DEBUG: Utilization already exists for {item.brand} {item.size_ml} in bill {item.bill_no}")
                         continue

                    # Find matching BrandWarehouse entry
                    warehouse_qs = BrandWarehouse.objects.filter(capacity_size=int(item.size_ml))
                    if item_license_id:
                        warehouse_qs = warehouse_qs.filter(license_id=item_license_id)

                    warehouse_entry = warehouse_qs.filter(
                        brand_details__iexact=item.brand
                    ).first()
                    
                    if not warehouse_entry:
                        warehouse_entry = warehouse_qs.filter(
                            brand_details__icontains=item.brand,
                        ).first()
                        
                    if warehouse_entry:
                        print(
                            f"DEBUG: Found warehouse entry {warehouse_entry} for {item.brand} "
                            f"(license_id={item_license_id or 'N/A'})"
                        )
                        
                        # Calculate quantity (pieces)
                        # We have item.cases. Need to convert to bottles/pieces if we store pieces in warehouse
                        # BrandWarehouse.current_stock is in UNTIS (pieces/bottles)
                        # We need bottles per case.
                        
                        # Get bottles per case from Master Table (BrandMlInCases)
                        from models.masters.supply_chain.transit_permit.models import BrandMlInCases
                        
                        bottles_per_case = int(getattr(item, 'bottles_per_case', 0) or 0)
                        
                        # Try to find specific configuration for this size
                        ml_config = BrandMlInCases.objects.filter(ml=int(warehouse_entry.capacity_size)).first()
                        if ml_config and ml_config.pieces_in_case:
                            bottles_per_case = int(ml_config.pieces_in_case)
                            print(f"DEBUG: Found ML configuration for {warehouse_entry.capacity_size}ml: {bottles_per_case} pieces/case")
                        else:
                            if bottles_per_case <= 0:
                                bottles_per_case = 1
                            print(
                                f"WARNING: No ML configuration found for {warehouse_entry.capacity_size}ml. "
                                f"Using fallback {bottles_per_case} from permit/default."
                            )
                        
                        total_pieces = int(item.cases) * bottles_per_case
                        
                        # Create Utilization Record
                        # This auto-deducts from BrandWarehouse via the save() method in BrandWarehouseUtilization model
                        utilization = BrandWarehouseUtilization.objects.create(
                            brand_warehouse=warehouse_entry,
                            license_id=item_license_id or str(getattr(warehouse_entry, 'license_id', '') or '').strip() or None,
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
                        print(
                            f"WARNING: No warehouse entry found for Brand: {item.brand}, "
                            f"Size: {item.size_ml}, license_id={item_license_id or 'N/A'}"
                        )
                        
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
