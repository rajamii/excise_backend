from rest_framework import viewsets, status, permissions, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db import transaction as db_transaction
from .models import HologramProcurement, HologramRequest, HologramRollsDetails
from .serializers import HologramProcurementSerializer, HologramRequestSerializer
from auth.workflow.models import Workflow, WorkflowStage, WorkflowTransition, Transaction
from models.masters.supply_chain.profile.models import SupplyChainUserProfile
import uuid

class HologramProcurementViewSet(viewsets.ModelViewSet):
    queryset = HologramProcurement.objects.all()
    serializer_class = HologramProcurementSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        
        queryset = super().get_queryset()
        
        if not user.is_authenticated:
            return queryset.none()
            
        # Role-based filtering
        role_name = user.role.name if hasattr(user, 'role') and user.role else ''
        
        if role_name in ['licensee', 'Licensee']:
            if hasattr(user, 'supply_chain_profile'):
                return queryset.filter(licensee=user.supply_chain_profile)
            return queryset.none()
            
        elif role_name in ['it_cell', 'IT Cell', 'IT-Cell', 'it-cell']:
            # IT Cell sees EVERYTHING (Tracking & Management)
            return queryset
            
        elif role_name in ['level_1', 'level_2', 'level_3', 'level_4', 'level_5', 'Site-Admin', 'site_admin', 'commissioner', 'Commissioner']:
            # Commissioner sees Forwarded + Decision History
            return queryset.filter(current_stage__name__in=[
                'Forwarded to Commissioner', 
                'Approved by Commissioner', 
                'Rejected by Commissioner'
            ])
            
        elif role_name in ['officer_in_charge', 'Officer In-Charge', 'OIC', 'officer-incharge']:
            # OIC sees Payment Completed (Pending Action) + Assigned (History)
            return queryset.filter(current_stage__name__in=[
                'Payment Completed', 
                'Cartoon Assigned'
            ])
            
        return queryset.none() # Default deny if role unknown
        return queryset.none() # Default deny if role unknown

    def perform_create(self, serializer):
        # Auto-generate Ref No
        ref_no = f"YB/6/BREW/{timezone.now().year}/{uuid.uuid4().hex[:6].upper()}"
        
        # Get initial workflow stage
        try:
            workflow = Workflow.objects.get(name='Hologram Procurement')
            initial_stage = WorkflowStage.objects.get(workflow=workflow, is_initial=True)
        except Workflow.DoesNotExist:
             # Fallback or error - Should be populated via command
             raise serializers.ValidationError("Workflow configuration missing.")

        instance = serializer.save(
            ref_no=ref_no,
            licensee=self.request.user.supply_chain_profile,
            workflow=workflow,
            current_stage=initial_stage,
            manufacturing_unit=self.request.user.supply_chain_profile.manufacturing_unit_name
        )
        
        # Log initial transaction
        Transaction.objects.create(
            application=instance,
            stage=initial_stage,
            performed_by=self.request.user,
            remarks='Hologram Procurement Application Submitted'
        )

    @action(detail=True, methods=['post'])
    def perform_action(self, request, pk=None):
        instance = self.get_object()
        action_name = request.data.get('action')
        remarks = request.data.get('remarks', '')
        
        if not action_name:
            return Response({'error': 'Action is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Find transition matching current stage and action
        transitions = WorkflowTransition.objects.filter(
            workflow=instance.workflow,
            from_stage=instance.current_stage
        )
        
        selected_transition = None
        for t in transitions:
            cond = t.condition or {}
            if cond.get('action') == action_name:
                selected_transition = t
                break
                
        if selected_transition:
            with db_transaction.atomic():
                instance.current_stage = selected_transition.to_stage
                
                # CRITICAL: Save carton_details if provided with the action
                if action_name == 'assign_cartons':
                    carton_details = request.data.get('carton_details')
                    if carton_details:
                        instance.carton_details = carton_details
                        # Sync to new table
                        self._sync_rolls_details(instance, carton_details)

                instance.save()
                
                # Check for Arrival Confirmation to ensure sync
                if action_name in ['confirm_arrival', 'arrival_confirmed', 'Confirm Arrival', 'confirm', 'Confirm']:
                     if instance.carton_details:
                         self._sync_rolls_details(instance, instance.carton_details)

                Transaction.objects.create(
                    application=instance,
                    stage=selected_transition.to_stage,
                    performed_by=self.request.user,
                    remarks=remarks or f"Action '{action_name}' performed"
                )
        else:
            # ALLOW UPDATE: If action is 'assign_cartons' and we have details, allow update without transition
            # This handles re-submission of carton details for records already in 'Cartoon Assigned' or 'Arrived' state
            
            if action_name == 'assign_cartons':
                carton_details = request.data.get('carton_details')
                if carton_details:
                    instance.carton_details = carton_details
                    self._sync_rolls_details(instance, carton_details)
            
            instance.save()
            
            Transaction.objects.create(
                application=instance,
                stage=instance.current_stage,
                performed_by=self.request.user,
                remarks=remarks or f"Action '{action_name}' performed"
            )
            
        return Response(self.get_serializer(instance).data)

    def _sync_rolls_details(self, procurement, carton_details):
        """
        Syncs JSON carton details to HologramRollsDetails table
        """
        try:
            print(f"DEBUG: Syncing {len(carton_details)} cartons to HologramRollsDetails for {procurement.ref_no}")
            
            # Collect all procurement types for fallback logic
            proc_types = []
            if procurement.local_qty and procurement.local_qty > 0:
                proc_types.append('LOCAL')
            if procurement.export_qty and procurement.export_qty > 0:
                proc_types.append('EXPORT')
            if procurement.defence_qty and procurement.defence_qty > 0:
                proc_types.append('DEFENCE')
            
            # Default fallback type (for backward compatibility)
            default_proc_type = proc_types[0] if proc_types else 'LOCAL'
                
            for item in carton_details:
                carton_num = item.get('cartoonNumber') or item.get('cartoon_number') or item.get('carton_number')
                if not carton_num:
                    continue
                
                defaults = {
                     'type': item.get('type') or default_proc_type,
                     'from_serial': item.get('fromSerial') or item.get('from_serial'),
                     'to_serial': item.get('toSerial') or item.get('to_serial'),
                     'total_count': item.get('numberOfHolograms') or item.get('number_of_holograms') or item.get('total_count', 0),
                }
                
                try:
                    defaults['total_count'] = int(defaults['total_count'])
                except:
                    defaults['total_count'] = 0

                # Calculate from serials if count is missing (Fix for 0 issue)
                if defaults['total_count'] == 0 and defaults['from_serial'] and defaults['to_serial']:
                    try:
                        f = int(str(defaults['from_serial']))
                        t = int(str(defaults['to_serial']))
                        defaults['total_count'] = (t - f) + 1
                    except (ValueError, TypeError):
                        pass
                
                # Check for existence
                obj, created = HologramRollsDetails.objects.get_or_create(
                    procurement=procurement,
                    carton_number=carton_num,
                    defaults={
                        **defaults,
                        'available': defaults['total_count'],
                        'status': 'AVAILABLE'
                    }
                )
                
                if created:
                    # CRITICAL: Initialize HologramSerialRange for new roll
                    # Create initial AVAILABLE range covering the entire roll
                    from models.transactional.supply_chain.hologram.models import HologramSerialRange
                    
                    HologramSerialRange.objects.create(
                        roll=obj,
                        from_serial=defaults['from_serial'],
                        to_serial=defaults['to_serial'],
                        count=defaults['total_count'],
                        status='AVAILABLE',
                        description=f'Initial range for roll {carton_num}'
                    )
                    print(f"✅ Created initial HologramSerialRange for {carton_num}: {defaults['from_serial']}-{defaults['to_serial']}")
                    
                    # Update available_range field
                    obj.update_available_range()
                    print(f"✅ Initialized available_range for {carton_num}: {obj.available_range}")
                
                if not created:
                    # Update definition fields
                    obj.type = defaults['type']
                    obj.from_serial = defaults['from_serial']
                    obj.to_serial = defaults['to_serial']
                    obj.total_count = defaults['total_count']
                    
                    # Reset available if unused (assuming edit mode)
                    if obj.used == 0 and obj.damaged == 0:
                        obj.available = obj.total_count
                        obj.status = 'AVAILABLE'
                    
                    obj.save()
                    
        except Exception as e:
            print(f"ERROR: Failed to sync rolls details: {e}")
            import traceback
            traceback.print_exc()


class HologramRequestViewSet(viewsets.ModelViewSet):
    queryset = HologramRequest.objects.all()
    serializer_class = HologramRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        
        if not user.is_authenticated:
            return queryset.none()
            
        role_name = user.role.name if hasattr(user, 'role') and user.role else ''
        print(f"DEBUG: User: {user.username}, Role: '{role_name}'")
        
        if role_name in ['licensee', 'Licensee']:
            if hasattr(user, 'supply_chain_profile'):
                return queryset.filter(licensee=user.supply_chain_profile)
            return queryset.none()
            
        elif role_name in ['permit-section', 'Permit-Section', 'Permit Section']:
            # Allow Permit Section to see all requests to track status
            return queryset
            
        elif role_name in ['officer_in_charge', 'Officer In-Charge', 'OIC', 'officer-in-charge', 'Officer-In-Charge', 'officer-incharge', 'Officer-Incharge', 'Officer In Charge', 'Officer in Charge', 'Officer in charge']:
            # OIC sees ALL requests (no workflow filtering)
            # Production Complete is determined by available quantity in frontend, not workflow stage
            return queryset
            
        return queryset.none()

    def perform_create(self, serializer):
        ref_no = f"HRQ/{timezone.now().year}/{uuid.uuid4().hex[:6].upper()}"
        
        try:
            workflow = Workflow.objects.get(name='Hologram Request')
            initial_stage = WorkflowStage.objects.get(workflow=workflow, is_initial=True)
        except Workflow.DoesNotExist:
             raise serializers.ValidationError("Workflow configuration missing.")

        instance = serializer.save(
            ref_no=ref_no,
            licensee=self.request.user.supply_chain_profile,
            workflow=workflow,
            current_stage=initial_stage
        )

        Transaction.objects.create(
            application=instance,
            stage=initial_stage,
            performed_by=self.request.user,
            remarks='Hologram Production Request Submitted'
        )

    @action(detail=True, methods=['post'])
    def perform_action(self, request, pk=None):
        instance = self.get_object()
        action_name = request.data.get('action')
        remarks = request.data.get('remarks', '')
        issued_assets = request.data.get('issued_assets')

        print(f"DEBUG: perform_action. Ref: {instance.ref_no}, Current Stage: {instance.current_stage.name}, Action: {action_name}")
        print(f"DEBUG: issued_assets received: {issued_assets}")

        # CRITICAL FIX: Save both issued_assets and rolls_assigned immediately
        if issued_assets:
            instance.issued_assets = issued_assets
            instance.rolls_assigned = issued_assets  # Save for "Currently Issued Holograms" tab
            instance.save()
            print(f"DEBUG: Saved issued_assets and rolls_assigned for {instance.ref_no}: {len(issued_assets)} rolls")
        
        if not action_name:
            return Response({'error': 'Action is required'}, status=status.HTTP_400_BAD_REQUEST)

        transitions = WorkflowTransition.objects.filter(
            workflow=instance.workflow,
            from_stage=instance.current_stage
        )
        
        print(f"DEBUG: perform_action. Ref: {instance.ref_no}, Current Stage: {instance.current_stage.name}, Action: {action_name}")
        
        selected_transition = None
        for t in transitions:
            cond = t.condition or {}
            print(f"DEBUG: Checking transition to {t.to_stage.name} with cond {cond}")
            if cond.get('action') == action_name:
                selected_transition = t
                break
        
        if not selected_transition:
             print("DEBUG: No transition found")
             return Response({'error': 'Invalid action for current stage'}, status=status.HTTP_400_BAD_REQUEST)
        
        with db_transaction.atomic():
            # Refresh to ensure latest state
            instance.refresh_from_db()
            
            # Verify we are still in the 'from_stage'
            if instance.current_stage != selected_transition.from_stage:
                 print(f"DEBUG: Stage mismatch during atomic block. Expected {selected_transition.from_stage.name}, got {instance.current_stage.name}")
                 # Try to proceed if safe, or abort? 
                 # If stage changed, the transition might be invalid.
                 # Re-fetch transition? No, just fail for now to debug.
                 # Actually, let's just log and try to update if plausible.
            
            instance.current_stage = selected_transition.to_stage
            instance.save()
            
            # Verify persistence
            instance.refresh_from_db()
            if instance.current_stage != selected_transition.to_stage:
                print(f"DEBUG: CRITICAL FAIL - Save did not persist! Got {instance.current_stage.name}")
                raise serializers.ValidationError("Database update failed")

            print(f"DEBUG: Updated stage to {instance.current_stage.name}")
            
            Transaction.objects.create(
                application=instance,
                stage=selected_transition.to_stage,
                performed_by=self.request.user,
                remarks=remarks or f"Action '{action_name}' performed"
            )

            # CRITICAL: Dynamic Inventory Update
            # If assets were issued (e.g. on approval), update their status in Procurement inventory
            if issued_assets:
                self._update_inventory_status(instance, issued_assets)
                
                # CRITICAL FIX: Populate rolls_assigned for daily register dropdown
                instance.rolls_assigned = issued_assets
                instance.save(update_fields=['rolls_assigned'])
                print(f"DEBUG: Saved rolls_assigned for {instance.ref_no}: {len(issued_assets)} rolls")
            
        return Response(self.get_serializer(instance).data)

    def _update_inventory_status(self, request_instance, issued_assets):
        """
        Updates the status AND QUANTITY of allocated cartons in HologramProcurement
        """
        try:
            print(f"DEBUG: Updating inventory for {len(issued_assets)} assets. Payload: {issued_assets}")
            licensee = request_instance.licensee
            
            # Fetch all active procurements for this licensee to search within
            procurements = HologramProcurement.objects.filter(
                licensee=licensee
            ).all() 
            
            affected_procurements = {} # Map id -> instance
            
            for asset in issued_assets:
                cartoon_number = asset.get('cartoonNumber') or asset.get('cartoon_number')
                allocated_qty = int(asset.get('count') or asset.get('quantity') or 0)
                
                if not cartoon_number:
                    continue
                    
                # Find the procurement containing this cartoon
                found = False
                for proc in procurements:
                    carton_details = proc.carton_details or []
                    updated = False
                    
                    for detail in carton_details:
                        d_cartoon_num = detail.get('cartoon_number') or detail.get('cartoonNumber')
                        
                        if d_cartoon_num == cartoon_number:
                            # Found the carton! Update status and quantity.
                            current_status = detail.get('status', 'AVAILABLE')
                            current_available = int(detail.get('available_qty') if detail.get('available_qty') is not None else (detail.get('numberOfHolograms') or detail.get('total_count') or 0))
                            
                            print(f"DEBUG: Found carton {cartoon_number} in proc {proc.ref_no}")
                            print(f"DEBUG:   Current available_qty: {current_available}")
                            print(f"DEBUG:   Allocated qty: {allocated_qty}")
                            
                            # Deduct allocated quantity OR use provided remaining
                            # Check both camelCase and snake_case formats
                            remaining_arg = asset.get('remainingInCartoon') or asset.get('remaining_in_cartoon')
                            print(f"DEBUG:   Raw remainingInCartoon from payload: {remaining_arg}, Type: {type(remaining_arg)}")
                            print(f"DEBUG:   Condition check - is not None: {remaining_arg is not None}")
                            
                            if remaining_arg is not None:
                                new_available = int(remaining_arg)
                                print(f"DEBUG:   ✅ Using provided remaining balance: {new_available}")
                            else:
                                new_available = max(0, current_available - allocated_qty)
                                print(f"DEBUG:   ❌ Calculated remaining: {current_available} - {allocated_qty} = {new_available}")
                                
                            detail['available_qty'] = new_available
                            
                            # Update status if needed
                            if current_status != 'IN_USE':
                                detail['status'] = 'IN_USE'
                                print(f"DEBUG:   Updated status to IN_USE")
                            
                            # Mark procurement as updated
                            updated = True
                            print(f"DEBUG:   Carton {cartoon_number} updated! New available_qty: {new_available}")
                            
                            found = True
                            break 
                    
                    if updated:
                        proc.carton_details = carton_details # Force assignment to trigger save
                        affected_procurements[proc.id] = proc
                    
                    if found:
                        break # Done with this asset
            
            # Bulk save affected procurements
            for proc in affected_procurements.values():
                print(f"DEBUG: Saving procurement {proc.ref_no} (ID: {proc.id})")
                proc.save()
                print(f"DEBUG: Procurement {proc.ref_no} saved successfully!")
                
                # Sync quantity changes to HologramRollsDetails
                try:
                    for asset in issued_assets:
                         c_num = asset.get('cartoonNumber') or asset.get('cartoon_number')
                         a_qty = int(asset.get('count') or asset.get('quantity') or 0)
                         
                         if not c_num: continue
                         
                         try:
                             roll_obj = HologramRollsDetails.objects.get(
                                 procurement=proc,
                                 carton_number=c_num
                             )
                             
                             # Deduct from DB available count directly to ensure consistency
                             # Reload to be safe? No, we trust the flow.
                             # Wait, we should use the same logic as above or sync from the JSON we just solved?
                             # Better to calculate:
                             # roll_obj.available -= a_qty
                             
                             # Let's resync from the procurement details to be 100% sure
                             # Find the detail again
                             target_detail = next((d for d in proc.carton_details if (d.get('cartoon_number') == c_num or d.get('cartoonNumber') == c_num)), None)
                             
                             if target_detail:
                                 roll_obj.available = target_detail['available_qty']
                                 roll_obj.status = target_detail['status']
                                 roll_obj.save()
                                 print(f"DEBUG: Synced RollsDetails for {c_num}: Available now {roll_obj.available}")
                                 
                                 # CRITICAL: Create/Update HologramSerialRange entries for allocated range
                                 # This enables dynamic available range calculation
                                 from_serial = asset.get('fromSerial') or asset.get('from_serial')
                                 to_serial = asset.get('toSerial') or asset.get('to_serial')
                                 
                                 if from_serial and to_serial:
                                     from models.transactional.supply_chain.hologram.models import HologramSerialRange
                                     
                                     try:
                                         from_num = int(from_serial)
                                         to_num = int(to_serial)
                                         allocated_count = to_num - from_num + 1
                                         
                                         # Find AVAILABLE ranges that overlap with the allocated range
                                         available_ranges = HologramSerialRange.objects.filter(
                                             roll=roll_obj,
                                             status='AVAILABLE'
                                         ).order_by('from_serial')
                                         
                                         for avail_range in available_ranges:
                                             avail_from = int(avail_range.from_serial)
                                             avail_to = int(avail_range.to_serial)
                                             
                                             # Check if allocated range overlaps with this available range
                                             if from_num <= avail_to and to_num >= avail_from:
                                                 # There's an overlap - need to split
                                                 
                                                 if from_num == avail_from and to_num == avail_to:
                                                     # Exact match - mark as IN_USE (so Not In Use can release it)
                                                     avail_range.status = 'IN_USE'
                                                     avail_range.used_date = request_instance.usage_date if hasattr(request_instance, 'usage_date') else None
                                                     avail_range.reference_no = request_instance.ref_no
                                                     avail_range.save()
                                                     print(f"✅ Marked entire range as IN_USE: {from_serial}-{to_serial}")
                                                     
                                                 elif from_num == avail_from and to_num < avail_to:
                                                     # Allocated from start - split into IN_USE and AVAILABLE
                                                     # Create IN_USE range (so Not In Use can release it)
                                                     HologramSerialRange.objects.create(
                                                         roll=roll_obj,
                                                         from_serial=from_serial,
                                                         to_serial=to_serial,
                                                         count=allocated_count,
                                                         status='IN_USE',
                                                         used_date=request_instance.usage_date if hasattr(request_instance, 'usage_date') else None,
                                                         reference_no=request_instance.ref_no,
                                                         description=f'Allocated for request {request_instance.ref_no}'
                                                     )
                                                     # Update original to remaining AVAILABLE range
                                                     avail_range.from_serial = str(to_num + 1)
                                                     avail_range.count = avail_to - to_num
                                                     avail_range.save()
                                                     print(f"✅ Split range: IN_USE {from_serial}-{to_serial}, AVAILABLE {to_num + 1}-{avail_to}")
                                                     
                                                 elif from_num > avail_from and to_num == avail_to:
                                                     # Allocated from middle to end - split into AVAILABLE and IN_USE
                                                     # Create IN_USE range (so Not In Use can release it)
                                                     HologramSerialRange.objects.create(
                                                         roll=roll_obj,
                                                         from_serial=from_serial,
                                                         to_serial=to_serial,
                                                         count=allocated_count,
                                                         status='IN_USE',
                                                         used_date=request_instance.usage_date if hasattr(request_instance, 'usage_date') else None,
                                                         reference_no=request_instance.ref_no,
                                                         description=f'Allocated for request {request_instance.ref_no}'
                                                     )
                                                     # Update original to remaining AVAILABLE range
                                                     avail_range.to_serial = str(from_num - 1)
                                                     avail_range.count = from_num - 1 - avail_from + 1
                                                     avail_range.save()
                                                     print(f"✅ Split range: AVAILABLE {avail_from}-{from_num - 1}, IN_USE {from_serial}-{to_serial}")
                                                     
                                                 elif from_num > avail_from and to_num < avail_to:
                                                     # Allocated from middle - split into 3 parts: AVAILABLE, IN_USE, AVAILABLE
                                                     # Create IN_USE range (so Not In Use can release it)
                                                     HologramSerialRange.objects.create(
                                                         roll=roll_obj,
                                                         from_serial=from_serial,
                                                         to_serial=to_serial,
                                                         count=allocated_count,
                                                         status='IN_USE',
                                                         used_date=request_instance.usage_date if hasattr(request_instance, 'usage_date') else None,
                                                         reference_no=request_instance.ref_no,
                                                         description=f'Allocated for request {request_instance.ref_no}'
                                                     )
                                                     # Create second AVAILABLE range (after allocated)
                                                     HologramSerialRange.objects.create(
                                                         roll=roll_obj,
                                                         from_serial=str(to_num + 1),
                                                         to_serial=str(avail_to),
                                                         count=avail_to - to_num,
                                                         status='AVAILABLE',
                                                         description=f'Remaining range after allocation'
                                                     )
                                                     # Update original to first AVAILABLE range (before allocated)
                                                     avail_range.to_serial = str(from_num - 1)
                                                     avail_range.count = from_num - 1 - avail_from + 1
                                                     avail_range.save()
                                                     print(f"✅ Split into 3: AVAILABLE {avail_from}-{from_num - 1}, USED {from_serial}-{to_serial}, AVAILABLE {to_num + 1}-{avail_to}")
                                                 
                                                 break  # Found and processed the overlapping range
                                         
                                         # Update available_range field to reflect new state
                                         roll_obj.update_available_range()
                                         print(f"✅ Updated available_range for {c_num}: {roll_obj.available_range}")
                                         
                                     except (ValueError, TypeError) as e:
                                         print(f"⚠️ Could not parse serial numbers for range splitting: {e}")
                                         # Fallback: Just create a USED entry without splitting
                                         HologramSerialRange.objects.get_or_create(
                                             roll=roll_obj,
                                             from_serial=from_serial,
                                             to_serial=to_serial,
                                             defaults={
                                                 'count': a_qty,
                                                 'status': 'USED',
                                                 'used_date': request_instance.usage_date if hasattr(request_instance, 'usage_date') else None,
                                                 'reference_no': request_instance.ref_no,
                                                 'description': f'Allocated for request {request_instance.ref_no}'
                                             }
                                         )
                                         roll_obj.update_available_range()
                             
                         except HologramRollsDetails.DoesNotExist:
                             pass 
                             
                except Exception as ex:
                    print(f"ERROR: Failed to sync RollsDetails quantity: {ex}")
                
        except Exception as e:
            print(f"ERROR: Failed to update inventory status: {str(e)}")
            import traceback
            traceback.print_exc()


from .models import DailyHologramRegister
from .serializers import DailyHologramRegisterSerializer, HologramRollsDetailsSerializer

class DailyHologramRegisterViewSet(viewsets.ModelViewSet):
    queryset = DailyHologramRegister.objects.all()  # FIXED: was 'dataset' which DRF ignores
    serializer_class = DailyHologramRegisterSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return DailyHologramRegister.objects.none()
            
        role_name = user.role.name if hasattr(user, 'role') and user.role else ''
        
        # OIC / Licensee Access - Return entries for their licensee profile
        # Also support OIC roles which may use fallback profile
        if role_name in ['licensee', 'Licensee']:
            if hasattr(user, 'supply_chain_profile'):
                return DailyHologramRegister.objects.filter(licensee=user.supply_chain_profile)
            return DailyHologramRegister.objects.none()
                
        # IT Cell / Admin / OIC Access (View All)
        if role_name in ['it_cell', 'IT Cell', 'IT-Cell', 'Site-Admin', 'site_admin',
                         'officer_in_charge', 'Officer In-Charge', 'OIC', 
                         'officer-in-charge', 'Officer-In-Charge', 'officer-incharge', 'Officer-Incharge',
                         'Officer In Charge', 'Officer in Charge', 'Officer in charge']:
             return DailyHologramRegister.objects.all()
             
        return DailyHologramRegister.objects.none()

    def perform_create(self, serializer):
        try:
            # Ensure licensee is set from the logged-in user
            if hasattr(self.request.user, 'supply_chain_profile'):
                try:
                    profile = self.request.user.supply_chain_profile
                    instance = serializer.save(licensee=profile)
                except Exception as e:
                    print(f"ERROR: accessing supply_chain_profile: {e}")
                    raise serializers.ValidationError(f"User profile error: {str(e)}")
            else:
                # DEBUG fallback
                print(f"DEBUG: User {self.request.user.username} has no supply_chain_profile.")
                # if self.request.user.is_superuser: # Unblock for now
                if True:
                    from models.masters.supply_chain.profile.models import SupplyChainUserProfile
                    first_profile = SupplyChainUserProfile.objects.first()
                    if first_profile:
                        print(f"DEBUG: Fallback to first available profile: {first_profile.manufacturing_unit_name}")
                        instance = serializer.save(licensee=first_profile)
                    else:
                        raise serializers.ValidationError("No profile found.")
                
            # CRITICAL: Update Procurement Inventory
            self._update_procurement_usage(instance)
            
            # CRITICAL: Update Request Status to 'Production Completed'
            if instance.hologram_request:
                try:
                    req = instance.hologram_request
                    # Transition to 'Production Completed'
                    from auth.workflow.models import WorkflowStage, WorkflowTransition, Transaction
                    
                    if req.current_stage and req.current_stage.name == 'In Use':
                        # Find the next stage
                        completed_stage = WorkflowStage.objects.filter(workflow=req.workflow, name='Production Completed').first()
                        
                        if completed_stage:
                            req.current_stage = completed_stage
                            req.save()
                            print(f"DEBUG: Auto-completed HologramRequest {req.ref_no}")
                            
                            # Log Transaction
                            Transaction.objects.create(
                                application=req,
                                stage=completed_stage,
                                performed_by=self.request.user,
                                remarks='Hologram Production Completed via Daily Register'
                            )
                except Exception as e:
                    print(f"ERROR: Failed to update request status: {e}")
            else:
                # FALLBACK: Try to find request by reference number
                try:
                    if instance.reference_no:
                        req = HologramRequest.objects.filter(ref_no=instance.reference_no).first()
                        if req:
                            print(f"DEBUG: Found request by reference_no: {req.ref_no}")
                            # Link the entry to the request
                            instance.hologram_request = req
                            instance.save(update_fields=['hologram_request'])
                            
                            # Update request status
                            from auth.workflow.models import WorkflowStage, WorkflowTransition, Transaction
                            
                            if req.current_stage and req.current_stage.name == 'In Use':
                                completed_stage = WorkflowStage.objects.filter(workflow=req.workflow, name='Production Completed').first()
                                
                                if completed_stage:
                                    req.current_stage = completed_stage
                                    req.save()
                                    print(f"DEBUG: Auto-completed HologramRequest {req.ref_no} (via reference_no match)")
                                    
                                    Transaction.objects.create(
                                        application=req,
                                        stage=completed_stage,
                                        performed_by=self.request.user,
                                        remarks='Hologram Production Completed via Daily Register'
                                    )
                        else:
                            print(f"WARNING: No request found with ref_no={instance.reference_no}")
                except Exception as e:
                    print(f"ERROR: Failed to find/update request by reference_no: {e}")
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise serializers.ValidationError(f"Internal Server Error during save: {str(e)}")

    def _update_procurement_usage(self, instance):
        """
        Wrapper to ensure atomic transaction and row locking.
        """
        with db_transaction.atomic():
            self._update_procurement_usage_impl(instance)

    def _update_procurement_usage_impl(self, instance):
        """
        Updates the usage and available quantity in the original HologramProcurement
        based on the DailyHologramRegister entry.
        Also updates usage_history JSON and creates HologramSerialRange records.
        """
        print(f"\n{'='*80}")
        print(f"🔥 _update_procurement_usage_impl CALLED")
        print(f"{'='*80}")
        print(f"Entry ID: {instance.id if instance.id else 'NEW'}")
        print(f"Reference: {instance.reference_no}")
        print(f"Roll Range: {instance.roll_range}")
        print(f"Issued Qty: {instance.issued_qty}, Wastage Qty: {instance.wastage_qty}")
        print(f"{'='*80}\n")
        
        try:
            carton_number = None
            # Extract carton number strictly
            # roll_range format usually "CARTON - Range X-Y" or "CARTON-X-Y"
            if instance.roll_range:
                # CRITICAL FIX: Handle multi-brand format like "a2_BRAND_1", "a2_BRAND_2"
                # Extract the base carton number before any "_BRAND_" suffix
                roll_range_str = instance.roll_range.strip()
                
                # Check if this is a multi-brand format
                if '_BRAND_' in roll_range_str:
                    # Multi-brand format: 'a1 - 1 - 50_BRAND_1'
                    # Extract the base part before '_BRAND_' and then get the first element (carton number)
                    parts = roll_range_str.split('_BRAND_')
                    base_range = parts[0].strip()  # 'a1 - 1 - 50'
                    # Now extract just the carton number (first part before ' - ')
                    carton_number = base_range.split(' - ')[0].strip()  # 'a1'
                    print(f"DEBUG: Multi-brand format detected. Extracted carton: '{carton_number}' from '{roll_range_str}'")
                # Try splitting by " - " first (standard format)
                elif ' - ' in roll_range_str:
                    parts = roll_range_str.split(' - ')
                    carton_number = parts[0].strip()
                # Fallback: try splitting by "-" if no spaces found (e.g. "a2-51-100")
                elif '-' in roll_range_str:
                    parts = roll_range_str.split('-')
                    carton_number = parts[0].strip()
                # Fallback: just use the whole string if no separators
                else:
                    carton_number = roll_range_str
            
            if not carton_number:
                print(f"DEBUG: No carton number extracted from '{instance.roll_range}'")
                return

            print(f"DEBUG: Updating usage for Carton '{carton_number}' (Issued: {instance.issued_qty}, Wastage: {instance.wastage_qty})")

            # Find matching procurement
            from .models import HologramProcurement
            procurements = HologramProcurement.objects.filter(licensee=instance.licensee)
            
            target_procurement = None
            target_detail_index = -1
            
            # Normalization helper
            def normalize(s): return str(s).upper().strip().replace(' ', '')
            target_key = normalize(carton_number)

            for proc in procurements:
                details = proc.carton_details or []
                for idx, detail in enumerate(details):
                    d_carton = detail.get('cartoonNumber') or detail.get('cartoon_number')
                    if normalize(d_carton) == target_key:
                        target_procurement = proc
                        target_detail_index = idx
                        break
                if target_procurement:
                    break
            
            if target_procurement and target_detail_index >= 0:
                detail = target_procurement.carton_details[target_detail_index]
                
                # Get HologramRollsDetails object
                roll_obj = None
                try:
                    roll_obj = HologramRollsDetails.objects.select_for_update().get(
                        procurement=target_procurement,
                        carton_number=carton_number
                    )
                except HologramRollsDetails.DoesNotExist:
                    print(f"ERROR: HologramRollsDetails not found for {carton_number}")
                    return
                
                # Get current counts
                total_count = roll_obj.total_count
                current_used = roll_obj.used
                current_damaged = roll_obj.damaged
                print(f"DEBUG: Current state - total: {total_count}, used: {current_used}, damaged: {current_damaged}")
                
                # Calculate new counts
                new_used = current_used + (instance.issued_qty or 0) 
                new_damaged = current_damaged + (instance.wastage_qty or 0)
                new_available = max(0, total_count - new_used - new_damaged)
                
                print(f"DEBUG: New state - available: {new_available}, used: {new_used}, damaged: {new_damaged}")
                
                # Update JSON in procurement
                detail['used_qty'] = new_used
                detail['damage_qty'] = new_damaged
                detail['available_qty'] = new_available
                detail['status'] = 'COMPLETED' if new_available == 0 else 'AVAILABLE'
                target_procurement.carton_details[target_detail_index] = detail 
                
                # Update balance
                deduct_qty = instance.issued_qty or 0
                if target_procurement.local_qty > 0:
                     target_procurement.local_qty = max(0, float(target_procurement.local_qty) - deduct_qty)
                elif target_procurement.export_qty > 0:
                     target_procurement.export_qty = max(0, float(target_procurement.export_qty) - deduct_qty)
                elif target_procurement.defence_qty > 0:
                     target_procurement.defence_qty = max(0, float(target_procurement.defence_qty) - deduct_qty)
                
                target_procurement.save()
                
                # ===== NEW: Update HologramRollsDetails with usage_history =====
                
                # Initialize usage_history if not exists
                if not roll_obj.usage_history:
                    roll_obj.usage_history = []
                
                from .models import HologramSerialRange
                
                print(f"=" * 80)
                print(f"🔥 DAILY REGISTER SAVE - RANGE SPLITTING DEBUG")
                print(f"=" * 80)
                print(f"Roll: {carton_number}")
                print(f"Issued Qty: {instance.issued_qty}")
                print(f"Wastage Qty: {instance.wastage_qty}")
                print(f"Issued Ranges: {instance.issued_ranges}")
                print(f"Wastage Ranges: {instance.wastage_ranges}")
                print(f"Issued From/To: {instance.issued_from} - {instance.issued_to}")
                print(f"Wastage From/To: {instance.wastage_from} - {instance.wastage_to}")
                print(f"=" * 80)
                
                # SPECIAL CASE: "Not Used" - if issued and wastage are both 0
                if (not instance.issued_qty or instance.issued_qty == 0) and (not instance.wastage_qty or instance.wastage_qty == 0):
                    print(f"⚠️ 'Not Used' case detected (Issued: 0, Wastage: 0)")
                    
                    try:
                        start_int = None
                        end_int = None
                        
                        # PRIORITY 1: Use allocated_from_serial and allocated_to_serial if available
                        # These fields are sent by the frontend for "Not In Use" entries
                        if hasattr(instance, 'allocated_from_serial') and hasattr(instance, 'allocated_to_serial'):
                            if instance.allocated_from_serial and instance.allocated_to_serial:
                                try:
                                    start_int = int(instance.allocated_from_serial)
                                    end_int = int(instance.allocated_to_serial)
                                    print(f"✅ Using allocated_from_serial/allocated_to_serial: {start_int}-{end_int}")
                                except (ValueError, TypeError):
                                    pass
                        
                        # FALLBACK: Use regex to extract range from roll_range string
                        if start_int is None or end_int is None:
                            import re
                            # Use regex to find all numbers in the string
                            # This handles "a2 - 51 - 100", "a1 - Range 1-50", "51-100", etc.
                            # We expect the last two numbers to be the start and end of the range
                            numbers = re.findall(r'\d+', instance.roll_range)
                            
                            if len(numbers) >= 2:
                                # Assume the last two numbers are the range
                                start_s = numbers[-2]
                                end_s = numbers[-1]
                                
                                start_int = int(start_s)
                                end_int = int(end_s)
                                
                                print(f"🔍 Parsed range via Regex: {start_int}-{end_int} (from '{instance.roll_range}')")
                        
                        if start_int is not None and end_int is not None:
                            # Fetch ALL IN_USE ranges for this roll
                            in_use_candidates = HologramSerialRange.objects.filter(roll=roll_obj, status='IN_USE')
                            
                            match_found = False
                            for candidate in in_use_candidates:
                                try:
                                    c_start = int(candidate.from_serial)
                                    c_end = int(candidate.to_serial)
                                    
                                    # Check for exact match OR overlap
                                    # We want to be generous here: if the candidate is fully contained in the target range, release it
                                    if c_start >= start_int and c_end <= end_int:
                                        print(f"✅ Found matching IN_USE range {c_start}-{c_end}. Converting to AVAILABLE.")
                                        candidate.status = 'AVAILABLE'
                                        candidate.description = f'Released from Not Used entry {instance.reference_no}'
                                        candidate.save()
                                        match_found = True
                                except ValueError:
                                    continue
                            
                            if not match_found:
                                print(f"⚠️ No matching IN_USE ranges found for {start_int}-{end_int}")
                                print(f"   Existing IN_USE ranges: {[f'{r.from_serial}-{r.to_serial}' for r in in_use_candidates]}")
                        else:
                            print(f"⚠️ Could not determine allocated range for Not In Use entry")

                    except Exception as e:
                        print(f"ERROR processing Not Used range: {e}")

                # Check existing IN_USE ranges
                existing_in_use = HologramSerialRange.objects.filter(roll=roll_obj, status='IN_USE')
                print(f"Existing IN_USE ranges: {existing_in_use.count()}")
                for r in existing_in_use:
                    print(f"  - {r.from_serial} to {r.to_serial} (status: {r.status})")
                print(f"=" * 80)
                
                # CRITICAL: Find and delete IN_USE ranges that will be split
                # Collect all serials that will be marked as USED or DAMAGED
                used_serials = set()
                damaged_serials = set()
                
                # Collect USED serials
                if instance.issued_qty and instance.issued_qty > 0:
                    issued_ranges = instance.issued_ranges or []
                    if issued_ranges:
                        for issued_range in issued_ranges:
                            from_s = issued_range.get('fromSerial') or issued_range.get('from_serial')
                            to_s = issued_range.get('toSerial') or issued_range.get('to_serial')
                            try:
                                from_num = int(from_s)
                                to_num = int(to_s)
                                for serial in range(from_num, to_num + 1):
                                    used_serials.add(serial)
                            except (ValueError, TypeError):
                                pass
                    else:
                        try:
                            from_num = int(instance.issued_from)
                            to_num = int(instance.issued_to)
                            for serial in range(from_num, to_num + 1):
                                used_serials.add(serial)
                        except (ValueError, TypeError):
                            pass
                
                # Collect DAMAGED serials
                if instance.wastage_qty and instance.wastage_qty > 0:
                    wastage_ranges = instance.wastage_ranges or []
                    if wastage_ranges:
                        for wastage_range in wastage_ranges:
                            from_s = wastage_range.get('fromSerial') or wastage_range.get('from_serial')
                            to_s = wastage_range.get('toSerial') or wastage_range.get('to_serial')
                            try:
                                from_num = int(from_s)
                                to_num = int(to_s)
                                for serial in range(from_num, to_num + 1):
                                    damaged_serials.add(serial)
                            except (ValueError, TypeError):
                                pass
                    else:
                        try:
                            from_num = int(instance.wastage_from)
                            to_num = int(instance.wastage_to)
                            for serial in range(from_num, to_num + 1):
                                damaged_serials.add(serial)
                        except (ValueError, TypeError):
                            pass
                
                
                print(f"📊 Collected serials from current entry:")
                print(f"   Used serials: {len(used_serials)} - Sample: {sorted(list(used_serials))[:10] if used_serials else 'None'}")
                print(f"   Damaged serials: {len(damaged_serials)} - Sample: {sorted(list(damaged_serials))[:10] if damaged_serials else 'None'}")
                
                # CRITICAL FIX: Also collect used/damaged serials from ALL OTHER daily register entries for this same roll
                # This prevents duplicate AVAILABLE ranges in multi-brand scenarios
                print(f"🔍 Checking for OTHER daily register entries using roll {carton_number}...")
                other_entries = DailyHologramRegister.objects.filter(
                    cartoon_number=carton_number,
                    hologram_type=roll_obj.type
                ).exclude(id=instance.id)  # Exclude the current entry being saved
                
                print(f"   Found {other_entries.count()} other entries for this roll")
                
                for other_entry in other_entries:
                    # Collect USED serials from other entries
                    if other_entry.issued_qty and other_entry.issued_qty > 0:
                        other_issued_ranges = other_entry.issued_ranges or []
                        if other_issued_ranges:
                            for issued_range in other_issued_ranges:
                                from_s = issued_range.get('fromSerial') or issued_range.get('from_serial')
                                to_s = issued_range.get('toSerial') or issued_range.get('to_serial')
                                try:
                                    from_num = int(from_s)
                                    to_num = int(to_s)
                                    for serial in range(from_num, to_num + 1):
                                        used_serials.add(serial)
                                    print(f"   ✅ Added USED serials from other entry {other_entry.id}: {from_s}-{to_s}")
                                except (ValueError, TypeError):
                                    pass
                        else:
                            try:
                                from_num = int(other_entry.issued_from)
                                to_num = int(other_entry.issued_to)
                                for serial in range(from_num, to_num + 1):
                                    used_serials.add(serial)
                                print(f"   ✅ Added USED serials from other entry {other_entry.id}: {other_entry.issued_from}-{other_entry.issued_to}")
                            except (ValueError, TypeError):
                                pass
                    
                    # Collect DAMAGED serials from other entries
                    if other_entry.wastage_qty and other_entry.wastage_qty > 0:
                        other_wastage_ranges = other_entry.wastage_ranges or []
                        if other_wastage_ranges:
                            for wastage_range in other_wastage_ranges:
                                from_s = wastage_range.get('fromSerial') or wastage_range.get('from_serial')
                                to_s = wastage_range.get('toSerial') or wastage_range.get('to_serial')
                                try:
                                    from_num = int(from_s)
                                    to_num = int(to_s)
                                    for serial in range(from_num, to_num + 1):
                                        damaged_serials.add(serial)
                                    print(f"   ✅ Added DAMAGED serials from other entry {other_entry.id}: {from_s}-{to_s}")
                                except (ValueError, TypeError):
                                    pass
                        else:
                            try:
                                from_num = int(other_entry.wastage_from)
                                to_num = int(other_entry.wastage_to)
                                for serial in range(from_num, to_num + 1):
                                    damaged_serials.add(serial)
                                print(f"   ✅ Added DAMAGED serials from other entry {other_entry.id}: {other_entry.wastage_from}-{other_entry.wastage_to}")
                            except (ValueError, TypeError):
                                pass
                
                print(f"📊 FINAL collected serials (including other entries):")
                print(f"   Total used serials: {len(used_serials)} - Sample: {sorted(list(used_serials))[:10] if used_serials else 'None'}")
                print(f"   Total damaged serials: {len(damaged_serials)} - Sample: {sorted(list(damaged_serials))[:10] if damaged_serials else 'None'}")

                
                # Find IN_USE ranges that overlap with used/damaged serials
                in_use_ranges = HologramSerialRange.objects.filter(roll=roll_obj, status='IN_USE').order_by('from_serial')
                print(f"🔍 Found {in_use_ranges.count()} IN_USE range(s) to check for splitting")
                
                # Check for AVAILABLE ranges too - if we have them, we shouldn't run fallback
                available_ranges_check = HologramSerialRange.objects.filter(roll=roll_obj, status='AVAILABLE')
                
                if in_use_ranges.count() == 0 and available_ranges_check.count() == 0:
                    print(f"⚠️ WARNING: No IN_USE ranges found for roll {carton_number}")
                    print(f"   This might mean the allocation didn't create IN_USE ranges properly")
                    print(f"   Checking all ranges for this roll:")
                    all_ranges = HologramSerialRange.objects.filter(roll=roll_obj)
                    for r in all_ranges:
                        print(f"     - {r.from_serial} to {r.to_serial} (status: {r.status})")
                    
                    # FALLBACK: If no IN_USE ranges exist, we need to infer the allocated range
                    # from the request's rolls_assigned data
                    print(f"🔧 FALLBACK: Attempting to infer allocated range from request data")
                    
                    # Try to find the hologram request that was allocated
                    from .models import HologramRequest
                    try:
                        request = HologramRequest.objects.get(ref_no=instance.reference_no)
                        if request.rolls_assigned:
                            for assigned_roll in request.rolls_assigned:
                                if assigned_roll.get('cartoonNumber') == carton_number or assigned_roll.get('cartoon_number') == carton_number:
                                    # Found the allocated range
                                    alloc_from = assigned_roll.get('fromSerial') or assigned_roll.get('from_serial')
                                    alloc_to = assigned_roll.get('toSerial') or assigned_roll.get('to_serial')
                                    alloc_count = assigned_roll.get('count') or assigned_roll.get('quantity')
                                    
                                    print(f"✅ Found allocated range from request: {alloc_from}-{alloc_to} ({alloc_count} units)")
                                    
                                    # Create a virtual IN_USE range for processing
                                    try:
                                        alloc_from_num = int(alloc_from)
                                        alloc_to_num = int(alloc_to)
                                        
                                        # Calculate leftover serials
                                        allocated_serials = set(range(alloc_from_num, alloc_to_num + 1))
                                        leftover_serials = allocated_serials - used_serials - damaged_serials
                                        
                                        print(f"📊 Fallback range analysis:")
                                        print(f"   Total allocated: {len(allocated_serials)}")
                                        print(f"   Used: {len(allocated_serials & used_serials)}")
                                        print(f"   Damaged: {len(allocated_serials & damaged_serials)}")
                                        print(f"   Leftover: {len(leftover_serials)}")
                                        
                                        # Create AVAILABLE ranges for leftovers
                                        if leftover_serials:
                                            sorted_leftovers = sorted(leftover_serials)
                                            leftover_ranges = []
                                            current_start = sorted_leftovers[0]
                                            current_end = sorted_leftovers[0]
                                            
                                            for serial in sorted_leftovers[1:]:
                                                if serial == current_end + 1:
                                                    current_end = serial
                                                else:
                                                    leftover_ranges.append((current_start, current_end))
                                                    current_start = serial
                                                    current_end = serial
                                            leftover_ranges.append((current_start, current_end))
                                            
                                            print(f"📦 Creating {len(leftover_ranges)} AVAILABLE leftover range(s) via fallback")
                                            
                                            for left_from, left_to in leftover_ranges:
                                                leftover_count = left_to - left_from + 1
                                                HologramSerialRange.objects.create(
                                                    roll=roll_obj,
                                                    from_serial=str(left_from),
                                                    to_serial=str(left_to),
                                                    count=leftover_count,
                                                    status='AVAILABLE',
                                                    description=f'Leftover from allocation {instance.reference_no}'
                                                )
                                                print(f"✅ Created AVAILABLE leftover range (fallback): {left_from}-{left_to} ({leftover_count} units)")
                                        
                                    except (ValueError, TypeError) as e:
                                        print(f"⚠️ Could not parse allocated range: {e}")
                                    
                                    break
                    except HologramRequest.DoesNotExist:
                        print(f"⚠️ Could not find request {instance.reference_no} for fallback")
                
                for in_use_range in in_use_ranges:
                    try:
                        range_from = int(in_use_range.from_serial)
                        range_to = int(in_use_range.to_serial)
                        
                        # Check if this IN_USE range overlaps with used/damaged serials
                        range_serials = set(range(range_from, range_to + 1))
                        overlaps_used = bool(range_serials & used_serials)
                        overlaps_damaged = bool(range_serials & damaged_serials)
                        
                        if overlaps_used or overlaps_damaged:
                            print(f"🔄 Splitting IN_USE range {range_from}-{range_to}")
                            
                            # Save reference_no before deleting
                            ref_no = in_use_range.reference_no or instance.reference_no
                            
                            # Delete the original IN_USE range - we'll recreate the pieces
                            in_use_range.delete()
                            print(f"✅ Deleted IN_USE range {range_from}-{range_to}")
                            
                            # Find leftover serials (not used and not damaged)
                            leftover_serials = range_serials - used_serials - damaged_serials
                            
                            print(f"📊 Range analysis:")
                            print(f"   Total serials in range: {len(range_serials)}")
                            print(f"   Used serials: {len(range_serials & used_serials)}")
                            print(f"   Damaged serials: {len(range_serials & damaged_serials)}")
                            print(f"   Leftover serials: {len(leftover_serials)}")
                            
                            # Create AVAILABLE ranges for leftovers
                            if leftover_serials:
                                # Sort and group consecutive serials
                                sorted_leftovers = sorted(leftover_serials)
                                leftover_ranges = []
                                current_start = sorted_leftovers[0]
                                current_end = sorted_leftovers[0]
                                
                                for serial in sorted_leftovers[1:]:
                                    if serial == current_end + 1:
                                        current_end = serial
                                    else:
                                        leftover_ranges.append((current_start, current_end))
                                        current_start = serial
                                        current_end = serial
                                leftover_ranges.append((current_start, current_end))
                                
                                print(f"📦 Creating {len(leftover_ranges)} AVAILABLE leftover range(s)")
                                
                                # Create AVAILABLE range entries
                                for left_from, left_to in leftover_ranges:
                                    leftover_count = left_to - left_from + 1
                                    HologramSerialRange.objects.create(
                                        roll=roll_obj,
                                        from_serial=str(left_from),
                                        to_serial=str(left_to),
                                        count=leftover_count,
                                        status='AVAILABLE',
                                        description=f'Leftover from allocation {ref_no}'
                                    )
                                    print(f"✅ Created AVAILABLE leftover range: {left_from}-{left_to} ({leftover_count} units)")
                            else:
                                print(f"⚠️ No leftover serials found - entire range was used/damaged")
                    
                    except (ValueError, TypeError) as e:
                        print(f"⚠️ Could not parse IN_USE range {in_use_range.from_serial}-{in_use_range.to_serial}: {e}")
                
                # CRITICAL FIX: Also process existing AVAILABLE ranges
                # This handles multi-brand scenarios where the first entry already converted IN_USE to AVAILABLE
                # and the second entry needs to mark some of those AVAILABLE serials as USED
                available_ranges = HologramSerialRange.objects.filter(roll=roll_obj, status='AVAILABLE').order_by('from_serial')
                print(f"🔍 Found {available_ranges.count()} AVAILABLE range(s) to check for splitting")
                
                for avail_range in available_ranges:
                    try:
                        range_from = int(avail_range.from_serial)
                        range_to = int(avail_range.to_serial)
                        
                        # Check if this AVAILABLE range overlaps with used/damaged serials
                        range_serials = set(range(range_from, range_to + 1))
                        overlaps_used = bool(range_serials & used_serials)
                        overlaps_damaged = bool(range_serials & damaged_serials)
                        
                        if overlaps_used or overlaps_damaged:
                            print(f"🔄 Splitting AVAILABLE range {range_from}-{range_to}")
                            
                            # Delete the original AVAILABLE range - we'll recreate the pieces
                            avail_range.delete()
                            print(f"✅ Deleted AVAILABLE range {range_from}-{range_to}")
                            
                            # Find leftover serials (not used and not damaged)
                            leftover_serials = range_serials - used_serials - damaged_serials
                            
                            print(f"📊 AVAILABLE range analysis:")
                            print(f"   Total serials in range: {len(range_serials)}")
                            print(f"   Used serials from this range: {len(range_serials & used_serials)}")
                            print(f"   Damaged serials from this range: {len(range_serials & damaged_serials)}")
                            print(f"   Leftover serials: {len(leftover_serials)}")
                            
                            # Create new AVAILABLE ranges for leftovers
                            if leftover_serials:
                                # Sort and group consecutive serials
                                sorted_leftovers = sorted(leftover_serials)
                                leftover_ranges = []
                                current_start = sorted_leftovers[0]
                                current_end = sorted_leftovers[0]
                                
                                for serial in sorted_leftovers[1:]:
                                    if serial == current_end + 1:
                                        current_end = serial
                                    else:
                                        leftover_ranges.append((current_start, current_end))
                                        current_start = serial
                                        current_end = serial
                                leftover_ranges.append((current_start, current_end))
                                
                                print(f"📦 Re-creating {len(leftover_ranges)} AVAILABLE range(s) after removing used/damaged")
                                
                                # Create AVAILABLE range entries
                                for left_from, left_to in leftover_ranges:
                                    leftover_count = left_to - left_from + 1
                                    HologramSerialRange.objects.create(
                                        roll=roll_obj,
                                        from_serial=str(left_from),
                                        to_serial=str(left_to),
                                        count=leftover_count,
                                        status='AVAILABLE',
                                        description=f'Remaining after usage recorded'
                                    )
                                    print(f"✅ Re-created AVAILABLE range: {left_from}-{left_to} ({leftover_count} units)")
                            else:
                                print(f"⚠️ No leftover serials - entire AVAILABLE range was used/damaged")
                    
                    except (ValueError, TypeError) as e:
                        print(f"⚠️ Could not parse AVAILABLE range {avail_range.from_serial}-{avail_range.to_serial}: {e}")

                
                # Now create USED ranges
                if instance.issued_qty and instance.issued_qty > 0:
                    issued_ranges = instance.issued_ranges or []
                    if issued_ranges:
                        for issued_range in issued_ranges:
                            usage_entry = {
                                'type': 'ISSUED',
                                'cartoonNumber': carton_number,
                                'issuedFromSerial': issued_range.get('fromSerial') or issued_range.get('from_serial'),
                                'issuedToSerial': issued_range.get('toSerial') or issued_range.get('to_serial'),
                                'issuedQuantity': issued_range.get('quantity'),
                                'date': str(instance.usage_date),
                                'referenceNo': instance.reference_no,
                                'brandName': instance.brand_details,
                                'brandDetails': instance.brand_details,
                                'bottleSize': instance.bottle_size,
                                'approvedBy': self.request.user.username if self.request else 'System',
                                'approvedAt': timezone.now().isoformat()
                            }
                            roll_obj.usage_history.append(usage_entry)
                            
                            # Create USED range
                            HologramSerialRange.objects.create(
                                roll=roll_obj,
                                from_serial=usage_entry['issuedFromSerial'],
                                to_serial=usage_entry['issuedToSerial'],
                                count=usage_entry['issuedQuantity'],
                                status='USED',
                                used_date=instance.usage_date,
                                reference_no=instance.reference_no,
                                brand_name=instance.brand_details,
                                bottle_size=instance.bottle_size,
                                description=f"Used on {instance.usage_date}"
                            )
                            print(f"✅ Created USED serial range: {usage_entry['issuedFromSerial']} - {usage_entry['issuedToSerial']}")
                    else:
                        # Legacy: single issued range
                        usage_entry = {
                            'type': 'ISSUED',
                            'cartoonNumber': carton_number,
                            'issuedFromSerial': instance.issued_from,
                            'issuedToSerial': instance.issued_to,
                            'issuedQuantity': instance.issued_qty,
                            'date': str(instance.usage_date),
                            'referenceNo': instance.reference_no,
                            'brandName': instance.brand_details,
                            'brandDetails': instance.brand_details,
                            'bottleSize': instance.bottle_size,
                            'approvedBy': self.request.user.username if self.request else 'System',
                            'approvedAt': timezone.now().isoformat()
                        }
                        roll_obj.usage_history.append(usage_entry)
                        
                        # Create USED range
                        HologramSerialRange.objects.create(
                            roll=roll_obj,
                            from_serial=instance.issued_from,
                            to_serial=instance.issued_to,
                            count=instance.issued_qty,
                            status='USED',
                            used_date=instance.usage_date,
                            reference_no=instance.reference_no,
                            brand_name=instance.brand_details,
                            bottle_size=instance.bottle_size,
                            description=f"Used on {instance.usage_date}"
                        )
                        print(f"✅ Created USED serial range: {instance.issued_from} - {instance.issued_to}")
                
                # Now create DAMAGED ranges
                if instance.wastage_qty and instance.wastage_qty > 0:
                    wastage_ranges = instance.wastage_ranges or []
                    if wastage_ranges:
                        for wastage_range in wastage_ranges:
                            usage_entry = {
                                'type': 'WASTAGE',
                                'cartoonNumber': carton_number,
                                'wastageFromSerial': wastage_range.get('fromSerial') or wastage_range.get('from_serial'),
                                'wastageToSerial': wastage_range.get('toSerial') or wastage_range.get('to_serial'),
                                'wastageQuantity': wastage_range.get('quantity'),
                                'date': str(instance.usage_date),
                                'damageReason': wastage_range.get('damageReason') or instance.damage_reason,
                                'referenceNo': instance.reference_no,
                                'reportedBy': self.request.user.username if self.request else 'System',
                                'approvedBy': self.request.user.username if self.request else 'System',
                                'approvedAt': timezone.now().isoformat()
                            }
                            roll_obj.usage_history.append(usage_entry)
                            
                            # Create DAMAGED range
                            HologramSerialRange.objects.create(
                                roll=roll_obj,
                                from_serial=usage_entry['wastageFromSerial'],
                                to_serial=usage_entry['wastageToSerial'],
                                count=usage_entry['wastageQuantity'],
                                status='DAMAGED',
                                damage_date=instance.usage_date,
                                damage_reason=usage_entry['damageReason'],
                                reported_by=self.request.user.username if self.request else 'System',
                                description=usage_entry['damageReason'] or 'Damaged during production'
                            )
                            print(f"✅ Created DAMAGED serial range: {usage_entry['wastageFromSerial']} - {usage_entry['wastageToSerial']}")
                    else:
                        # Legacy: single wastage range
                        usage_entry = {
                            'type': 'WASTAGE',
                            'cartoonNumber': carton_number,
                            'wastageFromSerial': instance.wastage_from,
                            'wastageToSerial': instance.wastage_to,
                            'wastageQuantity': instance.wastage_qty,
                            'date': str(instance.usage_date),
                            'damageReason': instance.damage_reason,
                            'referenceNo': instance.reference_no,
                            'reportedBy': self.request.user.username if self.request else 'System',
                            'approvedBy': self.request.user.username if self.request else 'System',
                            'approvedAt': timezone.now().isoformat()
                        }
                        roll_obj.usage_history.append(usage_entry)
                        
                        # Create DAMAGED range
                        HologramSerialRange.objects.create(
                            roll=roll_obj,
                            from_serial=instance.wastage_from,
                            to_serial=instance.wastage_to,
                            count=instance.wastage_qty,
                            status='DAMAGED',
                            damage_date=instance.usage_date,
                            damage_reason=instance.damage_reason,
                            reported_by=self.request.user.username if self.request else 'System',
                            description=instance.damage_reason or 'Damaged during production'
                        )
                        print(f"✅ Created DAMAGED serial range: {instance.wastage_from} - {instance.wastage_to}")
                
                # Update HologramRollsDetails counts and save
                roll_obj.used = new_used
                roll_obj.damaged = new_damaged
                roll_obj.available = new_available
                roll_obj.status = detail['status']
                roll_obj.save()
                
                # Recalculate available count from AVAILABLE ranges
                available_ranges = HologramSerialRange.objects.filter(roll=roll_obj, status='AVAILABLE')
                total_available = sum(r.count for r in available_ranges)
                if total_available != roll_obj.available:
                    roll_obj.available = total_available
                    roll_obj.save(update_fields=['available'])
                    print(f"✅ Updated roll.available to {total_available} from AVAILABLE ranges")
                
                # CRITICAL: Update status based on available count
                if roll_obj.available == 0:
                    roll_obj.status = 'COMPLETED'
                    print(f"✅ Status changed to COMPLETED (no holograms left)")
                elif roll_obj.available > 0 and roll_obj.available < roll_obj.total_count:
                    # Has some available, but not all - could be IN_USE or AVAILABLE
                    # Check if there are any IN_USE ranges
                    in_use_count = HologramSerialRange.objects.filter(roll=roll_obj, status='IN_USE').count()
                    if in_use_count > 0:
                        roll_obj.status = 'IN_USE'
                        print(f"✅ Status remains IN_USE (has IN_USE ranges)")
                    else:
                        roll_obj.status = 'AVAILABLE'
                        print(f"✅ Status changed to AVAILABLE (has {roll_obj.available} holograms available)")
                elif roll_obj.available == roll_obj.total_count:
                    roll_obj.status = 'AVAILABLE'
                    print(f"✅ Status changed to AVAILABLE (fully available)")
                
                roll_obj.save(update_fields=['status'])
                
                # CRITICAL FIX: Sync these changes back to the HologramProcurement JSON
                # This ensures that APIs reading from carton_details (JSON) see the same data as those reading from HologramRollsDetails (Table)
                try:
                    proc_to_update = roll_obj.procurement
                    # Reload procurement to get latest JSON
                    proc_to_update.refresh_from_db()
                    
                    if proc_to_update.carton_details:
                        json_updated = False
                        updated_details = proc_to_update.carton_details
                        
                        for d in updated_details:
                            d_c_num = d.get('cartoonNumber') or d.get('cartoon_number')
                            if d_c_num and str(d_c_num).strip().upper() == str(carton_number).strip().upper():
                                # Found the matching entry in JSON - update it!
                                d['available_qty'] = roll_obj.available
                                d['used_qty'] = roll_obj.used
                                d['damaged_qty'] = roll_obj.damaged
                                d['status'] = roll_obj.status
                                json_updated = True
                                print(f"✅ Synced JSON for {carton_number}: Avail={roll_obj.available}, Used={roll_obj.used}, Status={roll_obj.status}")
                                break
                        
                        if json_updated:
                            proc_to_update.carton_details = updated_details
                            proc_to_update.save(update_fields=['carton_details'])
                            print(f"✅ Saved Procurement JSON updates")
                except Exception as json_e:
                    print(f"⚠️ Warning: Failed to sync Procurement JSON: {json_e}")
                
                # Update available_range to reflect new state
                roll_obj.update_available_range()
                
                # CRITICAL VERIFICATION: Check if leftover ranges were actually created
                final_available_ranges = HologramSerialRange.objects.filter(roll=roll_obj, status='AVAILABLE')
                print(f"🔍 FINAL VERIFICATION - AVAILABLE ranges in database:")
                for r in final_available_ranges:
                    print(f"   - {r.from_serial} to {r.to_serial} ({r.count} units, status: {r.status})")
                print(f"📊 Final available_range field: {roll_obj.available_range}")
                
                print(f"✅ Updated HologramRollsDetails - available: {roll_obj.available}, used: {roll_obj.used}, damaged: {roll_obj.damaged}")
                print(f"✅ Status: {roll_obj.status}, Available Range: {roll_obj.available_range}")
                print(f"✅ Usage history entries: {len(roll_obj.usage_history)}")
                
        except Exception as e:
            print(f"ERROR updating procurement usage: {e}")
            import traceback
            traceback.print_exc()

class HologramRollsDetailsViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = HologramRollsDetails.objects.all()
    serializer_class = HologramRollsDetailsSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return HologramRollsDetails.objects.none()
            
        role_name = user.role.name if hasattr(user, 'role') and user.role else ''
        
        # OIC / Licensee Access
        if role_name in ['licensee', 'Licensee', 'officer_in_charge', 'Officer In-Charge', 'OIC']:
            if hasattr(user, 'supply_chain_profile'):
                return HologramRollsDetails.objects.filter(procurement__licensee=user.supply_chain_profile)
                
        # IT Cell / Admin / Commissioner / OIC Access (View All)
        if role_name in ['it_cell', 'IT Cell', 'IT-Cell', 'Site-Admin', 'site_admin', 'commissioner', 'Commissioner', 'level_1', 'level_2', 'level_3', 'level_4', 'level_5', 'officer_in_charge', 'Officer In-Charge', 'OIC', 'officer-incharge']:
             return HologramRollsDetails.objects.all()
             
        return HologramRollsDetails.objects.none()
    
    def list(self, request, *args, **kwargs):
        """Override list to calculate and populate available_range for each roll"""
        print("=" * 80)
        print("🔥 HologramRollsDetailsViewSet.list() CALLED")
        print("=" * 80)
        
        queryset = self.filter_queryset(self.get_queryset())
        
        print(f"Queryset count: {queryset.count()}")
        
        # Update available_range for all rolls in queryset
        roll_ids = []
        for roll in queryset:
            print(f"Updating available_range for roll {roll.carton_number}...")
            roll.update_available_range()
            print(f"  -> available_range = {roll.available_range}")
            roll_ids.append(roll.id)
        
        # Refresh queryset to get updated values
        queryset = self.get_queryset().filter(id__in=roll_ids)
        
        print(f"After refresh, queryset count: {queryset.count()}")
        for roll in queryset:
            print(f"Roll {roll.carton_number}: available_range = {roll.available_range}")
        
        # Now serialize and return
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            print(f"Serialized data (paginated): {serializer.data}")
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        print(f"Serialized data: {serializer.data}")
        return Response(serializer.data)
    
    def retrieve(self, request, *args, **kwargs):
        """Override retrieve to calculate and populate available_range"""
        instance = self.get_object()
        instance.update_available_range()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def serial_ranges(self, request, pk=None):
        """
        Get detailed serial ranges for a specific roll
        Returns ranges from HologramSerialRange table if available,
        otherwise generates from usage_history JSON
        """
        roll = self.get_object()
        
        # Try to get from HologramSerialRange table first
        from .models import HologramSerialRange
        from .serializers import HologramSerialRangeSerializer
        
        ranges = HologramSerialRange.objects.filter(roll=roll).order_by('from_serial')
        
        if ranges.exists():
            # Return from database table
            serializer = HologramSerialRangeSerializer(ranges, many=True)
            return Response({
                'source': 'database',
                'ranges': serializer.data,
                'total_count': ranges.count()
            })
        else:
            # Fallback: Generate from usage_history JSON
            usage_history = roll.usage_history or []
            serial_ranges = []
            
            # Calculate what serials have been used/damaged
            used_serials = set()
            
            for entry in usage_history:
                if entry.get('type') == 'ISSUED':
                    from_serial = entry.get('issuedFromSerial') or entry.get('fromSerial')
                    to_serial = entry.get('issuedToSerial') or entry.get('toSerial')
                    qty = entry.get('issuedQuantity') or entry.get('quantity') or 0
                    
                    if from_serial and to_serial:
                        # Extract numeric parts
                        from_num = self._extract_serial_number(from_serial)
                        to_num = self._extract_serial_number(to_serial)
                        
                        # Mark all serials in this range as used
                        for num in range(from_num, to_num + 1):
                            used_serials.add(num)
                    
                    serial_ranges.append({
                        'from_serial': from_serial,
                        'to_serial': to_serial,
                        'count': qty,
                        'status': 'USED',
                        'description': f"Used on {entry.get('date')}",
                        'used_date': entry.get('date'),
                        'reference_no': entry.get('referenceNo'),
                        'brand_name': entry.get('brandName'),
                        'bottle_size': entry.get('bottleSize'),
                        'brand_details': entry.get('brandDetails')
                    })
                    
                elif entry.get('type') in ['WASTAGE', 'DAMAGED']:
                    from_serial = entry.get('wastageFromSerial') or entry.get('fromSerial')
                    to_serial = entry.get('wastageToSerial') or entry.get('toSerial')
                    qty = entry.get('wastageQuantity') or entry.get('quantity') or 0
                    
                    if from_serial and to_serial:
                        # Extract numeric parts
                        from_num = self._extract_serial_number(from_serial)
                        to_num = self._extract_serial_number(to_serial)
                        
                        # Mark all serials in this range as damaged
                        for num in range(from_num, to_num + 1):
                            used_serials.add(num)
                    
                    serial_ranges.append({
                        'from_serial': from_serial,
                        'to_serial': to_serial,
                        'count': qty,
                        'status': 'DAMAGED',
                        'description': entry.get('damageReason') or 'Damaged',
                        'damage_date': entry.get('date'),
                        'damage_reason': entry.get('damageReason'),
                        'reported_by': entry.get('reportedBy') or entry.get('approvedBy')
                    })
            
            # Generate available range(s)
            if roll.available > 0:
                # Get the roll's full range
                from_num = self._extract_serial_number(roll.from_serial)
                to_num = self._extract_serial_number(roll.to_serial)
                prefix = roll.from_serial[:-len(str(from_num))] if from_num > 0 else roll.from_serial
                
                # Find available ranges (gaps in used_serials)
                available_ranges = []
                current_start = None
                
                for num in range(from_num, to_num + 1):
                    if num not in used_serials:
                        if current_start is None:
                            current_start = num
                    else:
                        if current_start is not None:
                            # End of available range
                            available_ranges.append({
                                'from': current_start,
                                'to': num - 1,
                                'count': num - current_start
                            })
                            current_start = None
                
                # Handle last range
                if current_start is not None:
                    available_ranges.append({
                        'from': current_start,
                        'to': to_num,
                        'count': to_num - current_start + 1
                    })
                
                # Add available ranges to response
                for avail_range in available_ranges:
                    from_serial = prefix + str(avail_range['from']).zfill(6)
                    to_serial = prefix + str(avail_range['to']).zfill(6)
                    
                    serial_ranges.append({
                        'from_serial': from_serial,
                        'to_serial': to_serial,
                        'count': avail_range['count'],
                        'status': 'AVAILABLE',
                        'description': 'Available for production use'
                    })
            
            return Response({
                'source': 'json',
                'ranges': serial_ranges,
                'total_count': len(serial_ranges)
            })
    
    def _extract_serial_number(self, serial: str) -> int:
        """Extract numeric part from serial string"""
        import re
        match = re.search(r'\d+$', serial or '')
        return int(match.group()) if match else 0




class CommissionerDashboardViewSet(viewsets.ViewSet):
    """
    ViewSet for Commissioner Dashboard - Track all hologram requests with complete flow
    """
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def daily_register_overview(self, request):
        """
        Get complete overview of all hologram requests for commissioner dashboard
        Shows: Applied, Under Process, Completed On Time, Completed Late, Overdue
        """
        from django.db.models import Q
        from datetime import datetime
        
        try:
            # Get all hologram requests
            requests = HologramRequest.objects.select_related(
                'licensee', 'workflow', 'current_stage'
            ).prefetch_related('transactions').all()
            
            result_data = []
            
            for req in requests:
                print(f"\n=== Processing Request: {req.ref_no} ===")
                print(f"Current Stage: {req.current_stage.name if req.current_stage else 'None'}")
                
                # Get submission transaction
                submission_txn = req.transactions.filter(
                    stage__is_initial=True
                ).order_by('timestamp').first()
                
                # Get approval transaction - check multiple possible stage names
                approval_txn = req.transactions.filter(
                    Q(stage__name__icontains='Approved') | 
                    Q(stage__name__icontains='In Use') |
                    Q(stage__name='Approved by Permit Section')
                ).order_by('timestamp').first()
                
                print(f"Approval Transaction: {approval_txn.stage.name if approval_txn else 'None'}")
                
                # Get daily register entries for this request
                daily_entries = DailyHologramRegister.objects.filter(
                    Q(hologram_request=req) | Q(reference_no=req.ref_no)
                ).order_by('created_at')
                
                print(f"Daily Register Entries: {daily_entries.count()}")
                
                # Determine status based on current stage
                status = 'APPLIED'
                completed_on_time = None
                is_overdue = False
                time_remaining = None
                deadline = None
                completion_date = None
                completion_time = None
                officer_name = None
                brands_entered = []
                
                # Check current stage to determine status
                if req.current_stage:
                    stage_name = req.current_stage.name.lower()
                    
                    # Check if completed
                    if 'completed' in stage_name or 'production completed' in stage_name:
                        status = 'COMPLETED'
                        print(f"Status: COMPLETED (from stage name)")
                    # Check if approved/in use
                    elif 'approved' in stage_name or 'in use' in stage_name:
                        status = 'UNDER_PROCESS'
                        print(f"Status: UNDER_PROCESS (from stage name)")
                    # Check if submitted/initial
                    elif 'submitted' in stage_name or req.current_stage.is_initial:
                        status = 'APPLIED'
                        print(f"Status: APPLIED (from stage name)")
                
                # Override status if we have daily register entries (means it's completed)
                if daily_entries.exists():
                    status = 'COMPLETED'
                    print(f"Status: COMPLETED (has daily register entries)")
                
                # Calculate deadline and time remaining if approved
                if approval_txn:
                    # Deadline is 5 PM on approval date (make timezone-aware)
                    from django.utils import timezone as django_timezone
                    
                    approval_date = approval_txn.timestamp.date()
                    deadline_naive = datetime.combine(approval_date, datetime.strptime('17:00', '%H:%M').time())
                    # Make deadline timezone-aware
                    deadline = django_timezone.make_aware(deadline_naive) if django_timezone.is_naive(deadline_naive) else deadline_naive
                    
                    # Check if completed
                    if status == 'COMPLETED' and daily_entries.exists():
                        last_entry = daily_entries.last()
                        completion_datetime = datetime.combine(
                            last_entry.usage_date,
                            datetime.strptime('00:00', '%H:%M').time()
                        )
                        if last_entry.created_at:
                            completion_datetime = last_entry.created_at
                        
                        # Make completion_datetime timezone-aware if needed
                        if django_timezone.is_naive(completion_datetime):
                            completion_datetime = django_timezone.make_aware(completion_datetime)
                        
                        completion_date = last_entry.usage_date.isoformat()
                        completion_time = last_entry.created_at.strftime('%H:%M:%S') if last_entry.created_at else '00:00:00'
                        completed_on_time = completion_datetime <= deadline
                        
                        # Get officer who entered the data
                        if last_entry.licensee:
                            officer_name = last_entry.licensee.manufacturing_unit_name
                        
                        # Get brands entered
                        for entry in daily_entries:
                            if entry.brand_details:
                                brands_entered.append({
                                    'brand': entry.brand_details,
                                    'bottleSize': entry.bottle_size or '',
                                    'quantity': entry.issued_qty or 0,
                                    'usageDate': entry.usage_date.isoformat()
                                })
                    elif status == 'UNDER_PROCESS':
                        # Check if overdue
                        now = django_timezone.now()  # Use timezone-aware now
                        if now > deadline:
                            is_overdue = True
                            time_remaining = f"Overdue by {int((now - deadline).total_seconds() / 3600)}h"
                        else:
                            hours_left = int((deadline - now).total_seconds() / 3600)
                            minutes_left = int(((deadline - now).total_seconds() % 3600) / 60)
                            time_remaining = f"{hours_left}h {minutes_left}m remaining"
                
                print(f"Final Status: {status}")
                
                result_data.append({
                    'id': req.id,
                    'referenceNo': req.ref_no,
                    'distilleryName': req.licensee.manufacturing_unit_name if req.licensee else 'Unknown',
                    'submissionDate': submission_txn.timestamp.isoformat() if submission_txn else req.submission_date.isoformat(),
                    'submissionTime': submission_txn.timestamp.strftime('%H:%M:%S') if submission_txn else '00:00:00',
                    'approvalDate': approval_txn.timestamp.date().isoformat() if approval_txn else None,
                    'approvalTime': approval_txn.timestamp.strftime('%H:%M:%S') if approval_txn else None,
                    'usageDate': req.usage_date.isoformat(),
                    'hologramType': req.hologram_type,
                    'quantity': req.quantity,
                    'status': status,
                    'completedOnTime': completed_on_time,
                    'isOverdue': is_overdue,
                    'timeRemaining': time_remaining,
                    'deadline': deadline.isoformat() if deadline else None,
                    'completionDate': completion_date,
                    'completionTime': completion_time,
                    'officerName': officer_name,
                    'brandsEntered': brands_entered,
                    'currentStage': req.current_stage.name if req.current_stage else 'Unknown'
                })
            
            # Calculate summary statistics
            total_entries = len(result_data)
            applied_count = sum(1 for r in result_data if r['status'] == 'APPLIED')
            under_process_count = sum(1 for r in result_data if r['status'] == 'UNDER_PROCESS')
            completed_on_time_count = sum(1 for r in result_data if r['status'] == 'COMPLETED' and r['completedOnTime'])
            completed_late_count = sum(1 for r in result_data if r['status'] == 'COMPLETED' and not r['completedOnTime'])
            overdue_count = sum(1 for r in result_data if r['isOverdue'])
            
            print(f"\n=== Summary ===")
            print(f"Total: {total_entries}, Applied: {applied_count}, Under Process: {under_process_count}")
            print(f"Completed On Time: {completed_on_time_count}, Completed Late: {completed_late_count}, Overdue: {overdue_count}")
            
            return Response({
                'summary': {
                    'totalEntries': total_entries,
                    'applied': applied_count,
                    'underProcess': under_process_count,
                    'completedOnTime': completed_on_time_count,
                    'completedLate': completed_late_count,
                    'overdue': overdue_count
                },
                'entries': result_data
            })
        except Exception as e:
            import traceback
            print(f"ERROR in daily_register_overview: {str(e)}")
            print(traceback.format_exc())
            return Response({
                'error': str(e),
                'summary': {
                    'totalEntries': 0,
                    'applied': 0,
                    'underProcess': 0,
                    'completedOnTime': 0,
                    'completedLate': 0,
                    'overdue': 0
                },
                'entries': []
            }, status=500)


class HologramMonthlyReportViewSet(viewsets.ViewSet):
    """
    ViewSet for generating monthly hologram reports
    Auto-calculates from approved daily register entries
    """
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def generate_report(self, request):
        """
        Generate monthly report for a specific month, year, and hologram type
        Query params:
        - month: Month name (e.g., 'January', 'jan')
        - year: Year (e.g., '2026')
        - hologram_type: Type (LOCAL, EXPORT, DEFENCE)
        - licensee_id: Optional licensee ID filter
        """
        from django.db.models import Sum, Q
        from datetime import datetime
        import calendar
        
        # Get query parameters
        month_param = request.query_params.get('month', '').lower()
        year_param = request.query_params.get('year', str(timezone.now().year))
        hologram_type = request.query_params.get('hologram_type', 'LOCAL').upper()
        licensee_id = request.query_params.get('licensee_id')
        
        # Month mapping
        month_map = {
            'jan': 1, 'january': 1,
            'feb': 2, 'february': 2,
            'mar': 3, 'march': 3,
            'apr': 4, 'april': 4,
            'may': 5,
            'jun': 6, 'june': 6,
            'jul': 7, 'july': 7,
            'aug': 8, 'august': 8,
            'sep': 9, 'september': 9,
            'oct': 10, 'october': 10,
            'nov': 11, 'november': 11,
            'dec': 12, 'december': 12
        }
        
        month_num = month_map.get(month_param, timezone.now().month)
        year_num = int(year_param)
        
        # Get licensee from user if not provided
        if not licensee_id and hasattr(request.user, 'supply_chain_profile'):
            licensee_id = request.user.supply_chain_profile.id
        
        # Build query filters
        filters = Q(
            usage_date__year=year_num,
            usage_date__month=month_num,
            hologram_type=hologram_type,
            approval_status='APPROVED'
        )
        
        if licensee_id:
            filters &= Q(licensee_id=licensee_id)
        
        # Get approved daily register entries for the month
        daily_entries = DailyHologramRegister.objects.filter(filters).order_by('usage_date', 'id')
        
        # Calculate previous month's closing balance
        prev_month = month_num - 1 if month_num > 1 else 12
        prev_year = year_num if month_num > 1 else year_num - 1
        
        # Get previous month's data
        prev_filters = Q(
            usage_date__year=prev_year,
            usage_date__month=prev_month,
            hologram_type=hologram_type,
            approval_status='APPROVED'
        )
        if licensee_id:
            prev_filters &= Q(licensee_id=licensee_id)
        
        prev_entries = DailyHologramRegister.objects.filter(prev_filters)
        
        # Calculate previous month totals
        prev_utilized = prev_entries.aggregate(total=Sum('issued_qty'))['total'] or 0
        prev_wastage = prev_entries.aggregate(total=Sum('wastage_qty'))['total'] or 0
        
        # Get fresh arrivals for current month (from HologramRollsDetails)
        arrival_filters = Q(
            received_date__year=year_num,
            received_date__month=month_num,
            type=hologram_type
        )
        if licensee_id:
            arrival_filters &= Q(procurement__licensee_id=licensee_id)
        
        arrivals = HologramRollsDetails.objects.filter(arrival_filters)
        fresh_arrivals = arrivals.aggregate(total=Sum('total_count'))['total'] or 0
        arrival_count = arrivals.count()
        
        # Calculate current month totals
        total_utilized = daily_entries.aggregate(total=Sum('issued_qty'))['total'] or 0
        total_wastage = daily_entries.aggregate(total=Sum('wastage_qty'))['total'] or 0
        utilization_count = daily_entries.filter(issued_qty__gt=0).count()
        wastage_count = daily_entries.filter(wastage_qty__gt=0).count()
        
        # Get opening stock (previous month's closing balance)
        # This should come from the previous month's report or initial procurement
        opening_stock = 0
        
        # Try to get from previous month's closing
        if prev_month and prev_year:
            # Get all rolls up to previous month
            all_prev_rolls = HologramRollsDetails.objects.filter(
                Q(received_date__year__lt=prev_year) |
                Q(received_date__year=prev_year, received_date__month__lte=prev_month),
                type=hologram_type
            )
            if licensee_id:
                all_prev_rolls = all_prev_rolls.filter(procurement__licensee_id=licensee_id)
            
            total_received = all_prev_rolls.aggregate(total=Sum('total_count'))['total'] or 0
            
            # Get all usage up to previous month
            all_prev_usage = DailyHologramRegister.objects.filter(
                Q(usage_date__year__lt=prev_year) |
                Q(usage_date__year=prev_year, usage_date__month__lte=prev_month),
                hologram_type=hologram_type,
                approval_status='APPROVED'
            )
            if licensee_id:
                all_prev_usage = all_prev_usage.filter(licensee_id=licensee_id)
            
            total_prev_utilized = all_prev_usage.aggregate(total=Sum('issued_qty'))['total'] or 0
            total_prev_wastage = all_prev_usage.aggregate(total=Sum('wastage_qty'))['total'] or 0
            
            opening_stock = total_received - total_prev_utilized - total_prev_wastage
        
        # Calculate closing balance
        closing_balance = opening_stock + fresh_arrivals - total_utilized - total_wastage
        
        # Build statement rows
        statement_rows = []
        
        # Group entries by date
        from collections import defaultdict
        entries_by_date = defaultdict(list)
        for entry in daily_entries:
            entries_by_date[entry.usage_date].append(entry)
        
        # Add arrival rows
        for arrival in arrivals:
            statement_rows.append({
                'rowType': 'ARRIVAL',
                'label': f"Arrival - {arrival.received_date.strftime('%d %b %Y')}",
                'freshArrival': arrival.total_count,
                'closingBalance': None,  # Will be calculated on frontend
                'meta': {
                    'cartoonNumber': arrival.carton_number,
                    'notes': f"Received {arrival.total_count} holograms"
                }
            })
        
        # Add utilization/wastage rows
        for date, entries in sorted(entries_by_date.items()):
            for entry in entries:
                row = {
                    'rowType': 'UTILIZATION',
                    'label': f"Utilization - {date.strftime('%d %b %Y')}",
                    'brandDetails': entry.brand_details or '-',
                    'bottleSize': entry.bottle_size or '-',
                    'utilizationFrom': entry.issued_from or '-',
                    'utilizationTo': entry.issued_to or '-',
                    'utilizationQty': entry.issued_qty,
                    'wastageFrom': entry.wastage_from or '-',
                    'wastageTo': entry.wastage_to or '-',
                    'wastageQty': entry.wastage_qty,
                    'leftOver': 0,  # Calculated on frontend
                    'closingBalance': None,  # Calculated on frontend
                    'meta': {
                        'referenceNo': entry.reference_no,
                        'cartoonNumber': entry.cartoon_number,
                        'serialRange': f"{entry.issued_from}-{entry.issued_to}" if entry.issued_from and entry.issued_to else None
                    }
                }
                
                # Add utilization details if multiple ranges
                if entry.issued_ranges:
                    row['utilizationDetails'] = [{
                        'rollName': entry.cartoon_number,
                        'ranges': [
                            {
                                'from': r.get('fromSerial'),
                                'to': r.get('toSerial'),
                                'qty': r.get('quantity')
                            }
                            for r in entry.issued_ranges
                        ]
                    }]
                
                # Add wastage details if multiple ranges
                if entry.wastage_ranges:
                    row['wastageDetails'] = [{
                        'rollName': entry.cartoon_number,
                        'ranges': [
                            {
                                'from': r.get('fromSerial'),
                                'to': r.get('toSerial'),
                                'qty': r.get('quantity')
                            }
                            for r in entry.wastage_ranges
                        ]
                    }]
                
                statement_rows.append(row)
        
        # Build response
        response_data = {
            'month': month_param,
            'year': year_param,
            'hologramType': hologram_type,
            'overviewSummary': {
                'openingStock': opening_stock,
                'totalArrivals': fresh_arrivals,
                'arrivalCount': arrival_count,
                'totalUtilized': total_utilized,
                'utilizationCount': utilization_count,
                'totalWastage': total_wastage,
                'wastageCount': wastage_count,
                'closingBalance': closing_balance
            },
            'statementRows': statement_rows,
            'approvedEntriesCount': daily_entries.count(),
            'previousMonthBalance': opening_stock
        }
        
        return Response(response_data)
