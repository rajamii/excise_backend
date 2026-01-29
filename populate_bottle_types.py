import os
import django
import sys

# Add the project directory to the sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.masters.supply_chain.transit_permit.models import TransitPermitBottleType

data = [
    {'id': 1, 'bottle_type': 'Glass', 'is_active': True},
    {'id': 2, 'bottle_type': 'Plastic', 'is_active': True},
    {'id': 3, 'bottle_type': 'PVC', 'is_active': True},
    {'id': 4, 'bottle_type': 'Aluminum', 'is_active': True},
]

print("Populating TransitPermitBottleType...")

for item in data:
    try:
        obj, created = TransitPermitBottleType.objects.update_or_create(
            id=item['id'],
            defaults={
                'bottle_type': item['bottle_type'],
                'is_active': item['is_active']
            }
        )
        action = "Created" if created else "Updated"
        print(f"{action}: {obj.id} - {obj.bottle_type}")
    except Exception as e:
        print(f"Error processing {item['bottle_type']}: {e}")

print("Done.")
