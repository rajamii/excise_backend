#!/usr/bin/env python
"""
Test script to simulate API response for rolls_assigned
"""
import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.transactional.supply_chain.hologram.models import HologramRequest
from models.transactional.supply_chain.hologram.serializers import HologramRequestSerializer

# Fetch all requests
requests = HologramRequest.objects.all()

print(f"\n{'='*80}")
print(f"API RESPONSE SIMULATION - HologramRequest")
print(f"{'='*80}\n")

for req in requests:
    # Simulate serialization (what the API returns)
    serializer = HologramRequestSerializer(req)
    data = serializer.data
    
    print(f"Ref: {data.get('ref_no')}")
    print(f"  Status: {data.get('status')}")
    print(f"  issued_assets: {data.get('issued_assets')}")
    print(f"  rolls_assigned: {data.get('rolls_assigned')}")
    print(f"  Has rolls_assigned: {bool(data.get('rolls_assigned'))}")
    print(f"  rolls_assigned length: {len(data.get('rolls_assigned', []))}")
    print()

print(f"{'='*80}\n")

# Test the filter logic
print("FILTER TEST:")
print("Requests with rolls_assigned populated:")
for req in requests:
    serializer = HologramRequestSerializer(req)
    data = serializer.data
    
    if data.get('rolls_assigned') and len(data.get('rolls_assigned', [])) > 0:
        print(f"  ✅ {data.get('ref_no')} - {len(data.get('rolls_assigned', []))} rolls")
    else:
        print(f"  ❌ {data.get('ref_no')} - No rolls assigned")

print()
