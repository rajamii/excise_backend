"""
Test complete allocation flow with range splitting
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.transactional.supply_chain.hologram.models import HologramRollsDetails, HologramSerialRange

print("=" * 80)
print("TESTING COMPLETE ALLOCATION FLOW")
print("=" * 80)

# Reset t1 to initial state
roll = HologramRollsDetails.objects.filter(carton_number='t1').first()

if not roll:
    print("❌ Roll t1 not found!")
    exit(1)

# Delete all ranges and recreate initial state
HologramSerialRange.objects.filter(roll=roll).delete()
HologramSerialRange.objects.create(
    roll=roll,
    from_serial='1',
    to_serial='1000',
    count=1000,
    status='AVAILABLE',
    description='Initial range'
)
roll.available = 1000
roll.used = 0
roll.save()
roll.update_available_range()

print(f"\n📦 Initial State - Roll: {roll.carton_number}")
print(f"   Available: {roll.available}")
print(f"   Available Range: {roll.available_range}")

# Simulate first allocation: 1-200
print(f"\n🔄 ALLOCATION 1: Allocating 1-200 (200 units)")

available_ranges = HologramSerialRange.objects.filter(roll=roll, status='AVAILABLE').order_by('from_serial')
first_range = available_ranges.first()

# Split: 1-200 USED, 201-1000 AVAILABLE
HologramSerialRange.objects.create(
    roll=roll,
    from_serial='1',
    to_serial='200',
    count=200,
    status='USED',
    reference_no='REF001',
    description='First allocation'
)
first_range.from_serial = '201'
first_range.count = 800
first_range.save()

roll.available = 800
roll.used = 200
roll.save()
roll.update_available_range()

print(f"   ✅ Available: {roll.available}")
print(f"   ✅ Available Range: {roll.available_range}")

# Simulate second allocation: 201-400
print(f"\n🔄 ALLOCATION 2: Allocating 201-400 (200 units)")

available_ranges = HologramSerialRange.objects.filter(roll=roll, status='AVAILABLE').order_by('from_serial')
second_range = available_ranges.first()

# Split: 201-400 USED, 401-1000 AVAILABLE
HologramSerialRange.objects.create(
    roll=roll,
    from_serial='201',
    to_serial='400',
    count=200,
    status='USED',
    reference_no='REF002',
    description='Second allocation'
)
second_range.from_serial = '401'
second_range.count = 600
second_range.save()

roll.available = 600
roll.used = 400
roll.save()
roll.update_available_range()

print(f"   ✅ Available: {roll.available}")
print(f"   ✅ Available Range: {roll.available_range}")

# Show final state
print(f"\n📊 Final Serial Ranges:")
ranges = HologramSerialRange.objects.filter(roll=roll).order_by('from_serial')
for r in ranges:
    status_icon = "🔴" if r.status == "USED" else "🟢"
    print(f"   {status_icon} {r.from_serial}-{r.to_serial}: {r.status} ({r.count} units) {r.reference_no or ''}")

print(f"\n✅ FINAL STATE:")
print(f"   Total: {roll.total_count}")
print(f"   Used: {roll.used}")
print(f"   Available: {roll.available}")
print(f"   Available Range: {roll.available_range}")

if roll.available_range == "401-1000":
    print(f"\n🎉 SUCCESS! Available range correctly shows 401-1000 after two allocations!")
else:
    print(f"\n⚠️ Unexpected result. Expected: 401-1000, Got: {roll.available_range}")

print("\n" + "=" * 80)
