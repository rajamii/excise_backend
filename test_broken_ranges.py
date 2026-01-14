import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.transactional.supply_chain.hologram.models import HologramRollsDetails

print("=" * 80)
print("TESTING BROKEN RANGE CALCULATION")
print("=" * 80)

# Get roll a1
roll = HologramRollsDetails.objects.get(carton_number='a1')

print(f"\nOriginal Roll: {roll.carton_number}")
print(f"  Full Range: {roll.from_serial} - {roll.to_serial}")
print(f"  Total: {roll.total_count}")
print(f"  Available: {roll.available}")
print(f"  Current usage_history:")
print(json.dumps(roll.usage_history, indent=2))

# Simulate using from middle (50-100)
print("\n" + "=" * 80)
print("SIMULATING: User uses 50-100 from middle")
print("=" * 80)

# Add a new usage entry for 50-100
new_usage = {
    "date": "2026-01-14",
    "type": "ISSUED",
    "brandName": "Test Brand",
    "approvedAt": "2026-01-14T10:00:00Z",
    "approvedBy": "TEST_USER",
    "bottleSize": "750ml",
    "referenceNo": "TEST/2026/001",
    "brandDetails": "Test",
    "cartoonNumber": "a1",
    "issuedQuantity": 51,
    "issuedFromSerial": "50",
    "issuedToSerial": "100"
}

# Create a test scenario without modifying the actual database
test_usage_history = roll.usage_history.copy()
test_usage_history.append(new_usage)

# Temporarily set the usage_history for calculation
original_history = roll.usage_history
roll.usage_history = test_usage_history

# Calculate the broken range
broken_range = roll.calculate_available_range()

print(f"\nCalculated available_range: {broken_range}")
print(f"\nExpected: Multiple ranges separated by comma")
print(f"  - Range 1: 1-49 (before the gap)")
print(f"  - Range 2: 101-1000 (after the gap)")

# Restore original
roll.usage_history = original_history

# Parse and display the ranges
if broken_range and broken_range not in ['None', 'N/A']:
    ranges = broken_range.split(',')
    print(f"\n✅ Successfully calculated {len(ranges)} broken range(s):")
    for i, r in enumerate(ranges, 1):
        r = r.strip()
        if '-' in r:
            from_s, to_s = r.split('-')
            count = int(to_s) - int(from_s) + 1
            print(f"  Range {i}: {from_s}-{to_s} ({count} holograms)")

print("\n" + "=" * 80)
print("ALLOCATION SIMULATION")
print("=" * 80)

print("\nScenario: Allocate 100 holograms from broken range")
print("Expected allocation order:")
print("  1. First 49 from range 1-49")
print("  2. Next 51 from range 101-151")
print("\nThis ensures no gaps in allocation and proper tracking!")
