
import os
import django
import sys

sys.stdout.reconfigure(encoding='utf-8')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.masters.supply_chain.status_master.models import StatusMaster

target_names = [
    'CancellationPending',
    'ForwardedCancellationToCommissioner',
    'ApprovedCancellationByCommissioner',
    'RejectedCancellationByCommissioner',
    'ForwardedCancellationToPermitSection',
    'RejectedCancellation'
]

print("Searching for specific statuses:")
for name in target_names:
    try:
        s = StatusMaster.objects.filter(status_name__iexact=name).first()
        if s:
            print(f"FOUND: {name} -> {s.status_code}")
        else:
            print(f"MISSING: {name}")
            # Try fuzzy match
            fuzzy = StatusMaster.objects.filter(status_name__icontains=name.split('To')[0]).all()
            if fuzzy:
                 print(f"  Did you mean one of these for '{name}'?")
                 for f in fuzzy:
                     print(f"    - {f.status_code}: {f.status_name}")
    except Exception as e:
        print(f"Error checking {name}: {e}")
