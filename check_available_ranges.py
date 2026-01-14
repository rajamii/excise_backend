import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.transactional.supply_chain.hologram.models import HologramRollsDetails

print("=" * 80)
print("CHECKING AVAILABLE RANGES IN DATABASE")
print("=" * 80)

rolls = HologramRollsDetails.objects.all().order_by('id')

for roll in rolls:
    print(f"\nRoll ID: {roll.id}")
    print(f"  Carton: {roll.carton_number}")
    print(f"  Type: {roll.type}")
    print(f"  Original Range: {roll.from_serial} - {roll.to_serial}")
    print(f"  Total: {roll.total_count}, Available: {roll.available}, Used: {roll.used}, Damaged: {roll.damaged}")
    print(f"  Status: {roll.status}")
    print(f"  Available Range: {roll.available_range}")
    print(f"  Usage History: {len(roll.usage_history) if roll.usage_history else 0} entries")

print("\n" + "=" * 80)
print(f"Total Rolls: {rolls.count()}")
print("=" * 80)
