"""
Debug script to check HologramSerialRange data for a specific cartoon
Run with: python manage.py shell < debug_serial_ranges.py
"""

from models.transactional.supply_chain.hologram.models import HologramRollsDetails, HologramSerialRange

# Find the cartoon that's showing wrong ranges
cartoon_number = "c1(a)"  # The cartoon mentioned in the issue

print(f"\n{'='*80}")
print(f"DEBUGGING SERIAL RANGES FOR CARTOON: {cartoon_number}")
print(f"{'='*80}\n")

# Get the roll details
try:
    roll = HologramRollsDetails.objects.get(carton_number=cartoon_number)
    
    print(f"Roll Details:")
    print(f"  Carton Number: {roll.carton_number}")
    print(f"  Type: {roll.type}")
    print(f"  From Serial: {roll.from_serial}")
    print(f"  To Serial: {roll.to_serial}")
    print(f"  Total Count: {roll.total_count}")
    print(f"  Available: {roll.available}")
    print(f"  Used: {roll.used}")
    print(f"  Damaged: {roll.damaged}")
    print(f"  Status: {roll.status}")
    print(f"  Available Range (calculated): {roll.available_range}")
    print()
    
    # Get all serial ranges for this roll
    serial_ranges = HologramSerialRange.objects.filter(roll=roll).order_by('from_serial')
    
    print(f"Serial Ranges ({serial_ranges.count()} total):")
    print(f"{'Status':<15} {'From':<10} {'To':<10} {'Count':<10} {'Ref No':<20} {'Description'}")
    print(f"{'-'*80}")
    
    for sr in serial_ranges:
        print(f"{sr.status:<15} {sr.from_serial:<10} {sr.to_serial:<10} {sr.count:<10} {sr.reference_no or 'N/A':<20} {sr.description or ''}")
    
    print()
    
    # Check if there are any requests using this cartoon
    from models.transactional.supply_chain.hologram.models import HologramRequest
    
    requests = HologramRequest.objects.filter(
        rolls_assigned__icontains=cartoon_number
    )
    
    print(f"\nRequests using this cartoon ({requests.count()} total):")
    for req in requests:
        print(f"\n  Reference: {req.ref_no}")
        print(f"  Status: {req.current_stage.name if req.current_stage else 'N/A'}")
        print(f"  Rolls Assigned:")
        for roll_data in req.rolls_assigned or []:
            c_num = roll_data.get('cartoonNumber') or roll_data.get('cartoon_number')
            if c_num == cartoon_number:
                print(f"    - Cartoon: {c_num}")
                print(f"      From Serial: {roll_data.get('fromSerial') or roll_data.get('from_serial')}")
                print(f"      To Serial: {roll_data.get('toSerial') or roll_data.get('to_serial')}")
                print(f"      Quantity: {roll_data.get('quantity') or roll_data.get('count')}")
    
except HologramRollsDetails.DoesNotExist:
    print(f"❌ Roll with cartoon number '{cartoon_number}' not found!")
    print("\nAvailable cartoons:")
    for roll in HologramRollsDetails.objects.all()[:10]:
        print(f"  - {roll.carton_number} ({roll.from_serial}-{roll.to_serial})")

print(f"\n{'='*80}\n")
