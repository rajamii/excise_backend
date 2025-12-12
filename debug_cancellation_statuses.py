
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.masters.supply_chain.status_master.models import StatusMaster

print("Searching for CANCELLATION related statuses:")
statuses = StatusMaster.objects.filter(status_name__icontains='Cancel')
for s in statuses:
    print(f"Code: {s.status_code}, Name: {s.status_name}")

print("\nSearching for statuses starting with CN:")
statuses = StatusMaster.objects.filter(status_code__startswith='CN')
for s in statuses:
    print(f"Code: {s.status_code}, Name: {s.status_name}")
