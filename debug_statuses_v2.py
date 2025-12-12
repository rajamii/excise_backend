
import os
import django
import sys

# Force utf-8
sys.stdout.reconfigure(encoding='utf-8')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.masters.supply_chain.status_master.models import StatusMaster

def safe_print(s):
    try:
        print(s)
    except:
        print(s.encode('utf-8', errors='ignore'))

print("--- START DUMP ---")
all_statuses = StatusMaster.objects.all().order_by('status_code')
for s in all_statuses:
    # Print as repr to show hidden chars
    print(f"Code: {s.status_code}, Name: {repr(s.status_name)}")
print("--- END DUMP ---")
