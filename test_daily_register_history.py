#!/usr/bin/env python
"""
Test script to check daily register entries for history tab
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.transactional.supply_chain.hologram.models import DailyHologramRegister

# Fetch all daily register entries
entries = DailyHologramRegister.objects.all()

print(f"\n{'='*80}")
print(f"DAILY HOLOGRAM REGISTER - HISTORY CHECK")
print(f"{'='*80}\n")

print(f"Total entries: {entries.count()}\n")

for entry in entries:
    print(f"ID: {entry.id}")
    print(f"  Reference No: {entry.reference_no}")
    print(f"  Cartoon Number: {entry.cartoon_number}")
    print(f"  Brand: {entry.brand_details}")
    print(f"  Hologram Type: {entry.hologram_type}")
    print(f"  Usage Date: {entry.usage_date}")
    print(f"  Total Qty: {entry.hologram_qty}")
    print(f"  Issued: {entry.issued_from} - {entry.issued_to} ({entry.issued_qty})")
    print(f"  Wastage: {entry.wastage_from} - {entry.wastage_to} ({entry.wastage_qty})")
    print(f"  Leftover: {entry.hologram_qty - entry.issued_qty - entry.wastage_qty}")
    print(f"  Status: is_fixed={entry.is_fixed}, approval_status={entry.approval_status}")
    print(f"  Approved By: {entry.approved_by.username if entry.approved_by else 'N/A'}")
    print(f"  Approved At: {entry.approved_at}")
    print()

# Filter for approved entries (what the history tab will show)
approved_entries = entries.filter(approval_status='APPROVED', is_fixed=True)
print(f"{'='*80}")
print(f"APPROVED ENTRIES (will show in history tab): {approved_entries.count()}")
print(f"{'='*80}\n")

for entry in approved_entries:
    print(f"✅ {entry.reference_no} - {entry.cartoon_number} - {entry.brand_details}")
    print(f"   Used: {entry.issued_qty}, Damaged: {entry.wastage_qty}, Leftover: {entry.hologram_qty - entry.issued_qty - entry.wastage_qty}")
    print()

print(f"{'='*80}\n")
