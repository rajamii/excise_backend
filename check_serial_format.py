import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.transactional.supply_chain.hologram.models import HologramRollsDetails

print("=" * 80)
print("CHECKING SERIAL NUMBER FORMAT")
print("=" * 80)

rolls = HologramRollsDetails.objects.all()

for roll in rolls:
    print(f"\nRoll: {roll.carton_number}")
    print(f"  from_serial: '{roll.from_serial}' (type: {type(roll.from_serial).__name__})")
    print(f"  to_serial: '{roll.to_serial}' (type: {type(roll.to_serial).__name__})")
    print(f"  available_range: '{roll.available_range}'")
    
    # Check usage history for actual serial format
    if roll.usage_history:
        print(f"  Usage history serials:")
        for entry in roll.usage_history:
            if entry.get('type') == 'ISSUED':
                print(f"    ISSUED: {entry.get('issuedFromSerial')} - {entry.get('issuedToSerial')}")
            elif entry.get('type') == 'WASTAGE':
                print(f"    WASTAGE: {entry.get('wastageFromSerial')} - {entry.get('wastageToSerial')}")
