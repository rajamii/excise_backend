import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.masters.supply_chain.transit_permit.models import BrandMlInCases

def verify():
    print("Verifying BrandMlInCases data:")
    for obj in BrandMlInCases.objects.all():
        print(f" - {obj}")

if __name__ == "__main__":
    verify()
