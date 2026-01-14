import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.transactional.supply_chain.hologram.models import HologramRollsDetails

print("=" * 80)
print("CHECKING USAGE HISTORY")
print("=" * 80)

roll = HologramRollsDetails.objects.get(carton_number='a1')

print(f"\nRoll: {roll.carton_number}")
print(f"Available: {roll.available}, Used: {roll.used}, Damaged: {roll.damaged}")
print(f"\nUsage History ({len(roll.usage_history)} entries):")
print(json.dumps(roll.usage_history, indent=2))

print("\n" + "=" * 80)
print("TESTING calculate_available_range()")
print("=" * 80)

result = roll.calculate_available_range()
print(f"Result: {result}")
