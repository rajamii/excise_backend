
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.masters.supply_chain.status_master.models import StatusMaster

print("Listing all StatusMaster entries:")
for status in StatusMaster.objects.all().order_by('status_code'):
    print(f"{status.status_code}: {status.status_name}")
