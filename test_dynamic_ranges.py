"""
Test script to verify dynamic available range calculation
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.transactional.supply_chain.hologram.models import HologramRollsDetails, HologramSerialRange

print("=" * 80)
print("TESTING DYNAMIC AVAILABLE RANGE CALCULATION")
print("=" * 80)

# Get roll t1
roll = HologramRollsDetails.objects.filter(carton_number='t1').first()

if not roll:
    print("❌ Roll t1 not found!")
    exit(1)

print(f"\n📦 Roll: {roll.carton_number}")
print(f"   Total: {roll.total_count}")
print(f"   Available: {roll.available}")
print(f"   From: {roll.from_serial}, To: {roll.to_serial}")

# Show current ranges
print(f"\n📊 Current Serial Ranges:")
ranges = HologramSerialRange.objects.filter(roll=roll).order_by('from_serial')
for r in ranges:
    print(f"   {r.from_serial}-{r.to_serial}: {r.status} ({r.count} units)")

# Calculate available range
available_range = roll.calculate_available_range()
print(f"\n✅ Current available_range: {available_range}")

# Simulate allocation of 1-200
print(f"\n🔄 SIMULATING ALLOCATION: 1-200 (200 units)")

# Find the AVAILABLE range that covers 1-200
available_ranges = HologramSerialRange.objects.filter(roll=roll, status='AVAILABLE').order_by('from_serial')

if available_ranges.exists():
    first_range = available_ranges.first()
    print(f"   Found AVAILABLE range: {first_range.from_serial}-{first_range.to_serial}")
    
    # Split the range: 1-200 becomes USED, 201-1000 stays AVAILABLE
    from_num = int(first_range.from_serial)
    to_num = int(first_range.to_serial)
    
    if from_num == 1 and to_num >= 200:
        # Mark 1-200 as USED
        HologramSerialRange.objects.create(
            roll=roll,
            from_serial='1',
            to_serial='200',
            count=200,
            status='USED',
            reference_no='TEST_REF_001',
            description='Test allocation'
        )
        print(f"   ✅ Created USED range: 1-200")
        
        # Update the original range to 201-1000
        first_range.from_serial = '201'
        first_range.count = to_num - 200
        first_range.save()
        print(f"   ✅ Updated AVAILABLE range: 201-{to_num}")
        
        # Update roll counts
        roll.available -= 200
        roll.used += 200
        roll.save()
        print(f"   ✅ Updated roll: available={roll.available}, used={roll.used}")
        
        # Recalculate available_range
        roll.update_available_range()
        new_available_range = roll.available_range
        
        print(f"\n✅ NEW available_range: {new_available_range}")
        print(f"   Expected: 201-1000")
        
        if new_available_range == "201-1000":
            print(f"\n🎉 SUCCESS! Available range dynamically updated!")
        else:
            print(f"\n⚠️ Unexpected result. Got: {new_available_range}")
        
        # Show final state
        print(f"\n📊 Final Serial Ranges:")
        ranges = HologramSerialRange.objects.filter(roll=roll).order_by('from_serial')
        for r in ranges:
            print(f"   {r.from_serial}-{r.to_serial}: {r.status} ({r.count} units)")
    else:
        print(f"   ❌ Range doesn't start at 1 or doesn't cover 200")
else:
    print(f"   ❌ No AVAILABLE ranges found")

print("\n" + "=" * 80)
