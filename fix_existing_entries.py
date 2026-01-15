#!/usr/bin/env python
"""
Fix existing daily register entries by linking them to requests and updating status
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.transactional.supply_chain.hologram.models import HologramRequest, DailyHologramRegister
from auth.workflow.models import WorkflowStage, Transaction
from django.contrib.auth import get_user_model

User = get_user_model()

print(f"\n{'='*80}")
print(f"FIXING EXISTING DAILY REGISTER ENTRIES")
print(f"{'='*80}\n")

# Get orphan entries (no hologram_request link)
orphan_entries = DailyHologramRegister.objects.filter(hologram_request__isnull=True, is_fixed=True)

print(f"Found {orphan_entries.count()} orphan entries\n")

for entry in orphan_entries:
    print(f"Processing entry ID: {entry.id}, Reference: {entry.reference_no}")
    
    # Try to find matching request
    req = HologramRequest.objects.filter(ref_no=entry.reference_no).first()
    
    if req:
        print(f"  ✅ Found matching request: {req.ref_no}")
        print(f"  Current status: {req.current_stage.name if req.current_stage else 'N/A'}")
        
        # Link the entry to the request
        entry.hologram_request = req
        entry.save(update_fields=['hologram_request'])
        print(f"  ✅ Linked entry to request")
        
        # Update request status if it's "In Use"
        if req.current_stage and req.current_stage.name == 'In Use':
            completed_stage = WorkflowStage.objects.filter(
                workflow=req.workflow, 
                name='Production Completed'
            ).first()
            
            if completed_stage:
                req.current_stage = completed_stage
                req.save()
                print(f"  ✅ Updated request status to: Production Completed")
                
                # Create transaction
                system_user = User.objects.filter(is_superuser=True).first()
                if system_user:
                    Transaction.objects.create(
                        application=req,
                        stage=completed_stage,
                        performed_by=system_user,
                        remarks='Status updated via fix script - Daily Register completed'
                    )
                    print(f"  ✅ Created transaction log")
            else:
                print(f"  ⚠️ Could not find 'Production Completed' stage")
        else:
            print(f"  ℹ️ Request not in 'In Use' status, skipping status update")
    else:
        print(f"  ❌ No matching request found for reference: {entry.reference_no}")
    
    print()

print(f"{'='*80}\n")
print("Fix complete! Refresh your browser to see the changes.")
print(f"{'='*80}\n")
