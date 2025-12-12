
import os
import django
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.masters.supply_chain.status_master.models import StatusMaster

names = [
    'CancellationPending',
    'ForwardedCancellationToCommissioner',
    'ApprovedCancellationByCommissioner',
    'RejectedCancellationByCommissioner',
    'ForwardedCancellationToPermitSection'
]

with open('cancellation_codes.txt', 'w') as f:
    for name in names:
        s = StatusMaster.objects.filter(status_name__iexact=name).first()
        if s:
            f.write(f"{name}: {s.status_code}\n")
        else:
            f.write(f"{name}: NOT FOUND\n")
            # Fuzzy check
            fuzzy = StatusMaster.objects.filter(status_name__icontains=name.split('To')[0]).all()
            for fs in fuzzy:
                 f.write(f"  Fuzzy match: {fs.status_code} - {fs.status_name}\n")

print("Done")
