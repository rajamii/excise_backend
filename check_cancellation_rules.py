
import os
import django
import sys

sys.stdout.reconfigure(encoding='utf-8')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.masters.supply_chain.status_master.models import WorkflowRule

print("Verifying Cancellation Rules:")
rules = WorkflowRule.objects.filter(current_status__status_code__in=['CN_00', 'RQ_14', 'RQ_19', 'RQ_20'])
for r in rules:
    print(f"{r.current_status.status_name} ({r.current_status.status_code}) + {r.action} ({r.allowed_role}) -> {r.next_status.status_name} ({r.next_status.status_code})")
