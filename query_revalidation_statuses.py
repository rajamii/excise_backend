import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.masters.supply_chain.status_master.models import StatusMaster

def query_statuses():
    """Query all revalidation status codes from the database."""
    print("\n" + "="*80)
    print("REVALIDATION STATUS CODES")
    print("="*80 + "\n")
    
    statuses = StatusMaster.objects.filter(status_code__startswith='RV').order_by('status_code')
    
    for status in statuses:
        print(f"{status.status_code}: {status.status_name}")
    
    print(f"\nTotal revalidation statuses found: {statuses.count()}")
    print("="*80 + "\n")

if __name__ == '__main__':
    query_statuses()
