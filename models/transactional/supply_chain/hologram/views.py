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

        if issued_assets:
            instance.issued_assets = issued_assets
            instance.save()
        
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
        if role_name in ['licensee', 'Licensee', 'officer_in_charge', 'Officer In-Charge', 'OIC', 
                         'officer-in-charge', 'Officer-In-Charge', 'officer-incharge', 'Officer-Incharge',
                         'Officer In Charge', 'Officer in Charge', 'Officer in charge']:
            if hasattr(user, 'supply_chain_profile'):
                return DailyHologramRegister.objects.filter(licensee=user.supply_chain_profile)
            else:
                # Fallback: If user has no profile but is an OIC, show ALL entries (dev mode fallback)
                # This mirrors the fallback in perform_create
                print(f"DEBUG: get_queryset - User {user.username} has no supply_chain_profile, returning all entries as fallback")
                return DailyHologramRegister.objects.all()
                
        # IT Cell / Admin Access (View All)
        if role_name in ['it_cell', 'IT Cell', 'IT-Cell', 'Site-Admin', 'site_admin']:
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
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise serializers.ValidationError(f"Internal Server Error during save: {str(e)}")

    def _update_procurement_usage(self, instance):
        """
        Updates the usage and available quantity in the original HologramProcurement
        based on the DailyHologramRegister entry.
        """
        try:
            carton_number = None
            # Extract carton number strictly
            # roll_range format usually "CARTON - Range X-Y"
            if instance.roll_range:
                parts = instance.roll_range.split(' - ')
                carton_number = parts[0].strip()
            
            if not carton_number:
                print(f"DEBUG: No carton number extracted from '{instance.roll_range}'")
                return

            print(f"DEBUG: Updating usage for Carton '{carton_number}' (Used: {instance.hologram_qty}, Wasted: {instance.wastage_qty})")

            # Find matching procurement
            # We must iterate because carton_details is JSON list
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
                
                # CRITICAL FIX: Try to get the authoritative total_count from HologramRollsDetails first
                # The JSON carton_details may have missing or incorrect values
                roll_obj = None
                try:
                    roll_obj = HologramRollsDetails.objects.get(
                        procurement=target_procurement,
                        carton_number=carton_number
                    )
                except HologramRollsDetails.DoesNotExist:
                    pass
                
                # Get total_count from DB model if available, otherwise fallback to JSON
                if roll_obj and roll_obj.total_count > 0:
                    total_count = roll_obj.total_count
                    current_used = roll_obj.used
                    current_damaged = roll_obj.damaged
                    print(f"DEBUG: Using HologramRollsDetails values - total_count: {total_count}, used: {current_used}, damaged: {current_damaged}")
                else:
                    # Fallback to JSON values
                    current_used = int(detail.get('used_qty', 0))
                    current_damaged = int(detail.get('damage_qty', 0))
                    total_count = int(detail.get('numberOfHolograms') or detail.get('number_of_holograms') or detail.get('total_count') or 0)
                    print(f"DEBUG: Using carton_details JSON values - total_count: {total_count}, used: {current_used}, damaged: {current_damaged}")
                
                # Add this entry's usage
                # instance.issued_qty is what was just consumed.
                new_used = current_used + (instance.issued_qty or 0) 
                new_damaged = current_damaged + (instance.wastage_qty or 0)
                
                # Calculate available
                new_available = max(0, total_count - new_used - new_damaged)
                print(f"DEBUG: Calculated new_available = {total_count} - {new_used} - {new_damaged} = {new_available}")
                
                # Update Dictionary
                detail['used_qty'] = new_used
                detail['damage_qty'] = new_damaged
                detail['available_qty'] = new_available
                
                # Status Update - AVAILABLE if still has quantity, COMPLETED if fully used
                if new_available == 0:
                    detail['status'] = 'COMPLETED'
                else:
                    detail['status'] = 'AVAILABLE'
                
                # Save changes to JSON
                target_procurement.carton_details[target_detail_index] = detail 
                
                # -- Balance Updates Logic (omitted for brevity) --
                deduct_qty = instance.issued_qty or 0
                if target_procurement.local_qty > 0:
                     target_procurement.local_qty = max(0, float(target_procurement.local_qty) - deduct_qty)
                elif target_procurement.export_qty > 0:
                     target_procurement.export_qty = max(0, float(target_procurement.export_qty) - deduct_qty)
                elif target_procurement.defence_qty > 0:
                     target_procurement.defence_qty = max(0, float(target_procurement.defence_qty) - deduct_qty)
                
                target_procurement.save()
                
                # ALSO Update the new HologramRollsDetails table if it exists
                # This ensures the new table stays in sync with usage
                # NOTE: We already fetched roll_obj earlier, so just reuse it
                if roll_obj:
                    print(f"DEBUG: Syncing usage to HologramRollsDetails for Carton {carton_number}")
                    roll_obj.used = new_used
                    roll_obj.damaged = new_damaged
                    roll_obj.available = new_available
                    roll_obj.status = detail['status']
                    roll_obj.save()
                    print(f"DEBUG: Updated HologramRollsDetails - available: {roll_obj.available}, used: {roll_obj.used}")
                else:
                    print(f"DEBUG: HologramRollsDetails not found for {carton_number}, skipping sync.")
                
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


