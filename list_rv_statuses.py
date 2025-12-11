import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.masters.supply_chain.status_master.models import StatusMaster

def list_revalidation_statuses():
    print("Searching Statuses containing 'Revalidation':")
    statuses = StatusMaster.objects.filter(status_name__icontains='Revalidation').order_by('status_code')
    for s in statuses:
        print(f"{s.status_code}: {s.status_name}")

if __name__ == '__main__':
    list_revalidation_statuses()
