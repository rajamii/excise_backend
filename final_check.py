
import os
import django
import sys

sys.stdout.reconfigure(encoding='utf-8')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.masters.supply_chain.status_master.models import StatusMaster

def check_status(name_part):
    s = StatusMaster.objects.filter(status_name__icontains=name_part).first()
    if s:
        print(f"MATCH: {name_part} -> {s.status_code} ({s.status_name})")
    else:
        print(f"NO MATCH: {name_part}")

check_status("ForwardedCancellationToCommissioner")
check_status("ApprovedCancellationBy")
check_status("RejectedCancellationBy")
check_status("CancellationPending")
