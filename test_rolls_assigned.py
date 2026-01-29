#!/usr/bin/env python
"""
Test script to check if rolls_assigned is being saved correctly
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.transactional.supply_chain.hologram.models import HologramRequest

# Fetch all requests
requests = HologramRequest.objects.all()

print(f"\n{'='*80}")
print(f"HOLOGRAM REQUESTS - rolls_assigned CHECK")
print(f"{'='*80}\n")

for req in requests:
    print(f"Ref: {req.ref_no}")
    print(f"  Status: {req.current_stage.name if req.current_stage else 'N/A'}")
    print(f"  issued_assets: {req.issued_assets}")
    print(f"  rolls_assigned: {req.rolls_assigned}")
    print(f"  issued_assets length: {len(req.issued_assets) if req.issued_assets else 0}")
    print(f"  rolls_assigned length: {len(req.rolls_assigned) if req.rolls_assigned else 0}")
    print()

print(f"{'='*80}\n")
