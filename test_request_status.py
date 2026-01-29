#!/usr/bin/env python
"""
Test script to check request status after daily register save
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.transactional.supply_chain.hologram.models import HologramRequest, DailyHologramRegister

print(f"\n{'='*80}")
print(f"HOLOGRAM REQUEST STATUS CHECK")
print(f"{'='*80}\n")

# Get all requests
requests = HologramRequest.objects.all()

for req in requests:
    print(f"Request: {req.ref_no}")
    print(f"  Current Stage: {req.current_stage.name if req.current_stage else 'N/A'}")
    print(f"  Workflow: {req.workflow.name if req.workflow else 'N/A'}")
    
    # Check if there are daily register entries for this request
    daily_entries = DailyHologramRegister.objects.filter(hologram_request=req)
    print(f"  Daily Register Entries: {daily_entries.count()}")
    
    for entry in daily_entries:
        print(f"    - Entry ID: {entry.id}, Reference: {entry.reference_no}, is_fixed: {entry.is_fixed}")
    
    print()

print(f"{'='*80}\n")

# Check daily register entries without request link
orphan_entries = DailyHologramRegister.objects.filter(hologram_request__isnull=True)
print(f"Daily Register Entries WITHOUT request link: {orphan_entries.count()}")
for entry in orphan_entries:
    print(f"  - ID: {entry.id}, Reference: {entry.reference_no}, is_fixed: {entry.is_fixed}")

print(f"\n{'='*80}\n")
