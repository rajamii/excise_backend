import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.transactional.supply_chain.hologram.models import HologramRollsDetails
from models.transactional.supply_chain.hologram.serializers import HologramRollsDetailsSerializer

print("=" * 80)
print("TESTING API SERIALIZER OUTPUT")
print("=" * 80)

rolls = HologramRollsDetails.objects.all()

for roll in rolls:
    # Update the available_range before serializing
    roll.update_available_range()
    
    serializer = HologramRollsDetailsSerializer(roll)
    data = serializer.data
    
    print(f"\nRoll: {data.get('carton_number')}")
    print(f"  available: {data.get('available')}")
    print(f"  available_range: {data.get('available_range')}")
    print(f"  from_serial: {data.get('from_serial')}")
    print(f"  to_serial: {data.get('to_serial')}")

print("\n" + "=" * 80)
print("API Response Preview:")
print("=" * 80)

serializer = HologramRollsDetailsSerializer(rolls, many=True)
print(json.dumps(serializer.data, indent=2))
