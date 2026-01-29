"""
Test script to verify leftover range creation
Run this after saving the daily register to check database state
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.transactional.supply_chain.hologram.models import HologramRollsDetails, HologramSerialRange

def test_leftover_ranges():
    print("=" * 80)
    print("🔍 TESTING LEFTOVER RANGE CREATION")
    print("=" * 80)
    
    # Find roll A1
    try:
        roll = HologramRollsDetails.objects.get(carton_number='A1')
        print(f"\n✅ Found roll: {roll.carton_number}")
        print(f"   Total: {roll.total_count}")
        print(f"   Available: {roll.available}")
        print(f"   Used: {roll.used}")
        print(f"   Damaged: {roll.damaged}")
        print(f"   Status: {roll.status}")
        print(f"   Available Range: {roll.available_range}")
        
        # Check serial ranges
        print(f"\n📊 Serial Ranges in Database:")
        ranges = HologramSerialRange.objects.filter(roll=roll).order_by('from_serial')
        
        if ranges.count() == 0:
            print("   ❌ NO RANGES FOUND!")
        else:
            for r in ranges:
                print(f"   - {r.from_serial} to {r.to_serial}: {r.status} ({r.count} units)")
        
        # Check specifically for leftover AVAILABLE range
        leftover_ranges = HologramSerialRange.objects.filter(
            roll=roll,
            status='AVAILABLE',
            from_serial='1'
        )
        
        if leftover_ranges.exists():
            print(f"\n✅ LEFTOVER RANGE FOUND!")
            for r in leftover_ranges:
                print(f"   {r.from_serial}-{r.to_serial} ({r.count} units)")
        else:
            print(f"\n❌ LEFTOVER RANGE NOT FOUND!")
            print(f"   Expected: 1-99 (99 units) with status AVAILABLE")
        
        # Verify available_range field
        print(f"\n📋 Available Range Field: {roll.available_range}")
        if '1-99' in roll.available_range:
            print(f"   ✅ Leftover range IS in available_range field")
        else:
            print(f"   ❌ Leftover range NOT in available_range field")
            print(f"   Expected: '1-99, 201-500' or similar")
        
    except HologramRollsDetails.DoesNotExist:
        print("❌ Roll A1 not found!")
    
    print("=" * 80)

if __name__ == '__main__':
    test_leftover_ranges()
