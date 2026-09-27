import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.transactional.supply_chain.ena_requisition_details.models import EnaRequisitionDetail
from models.transactional.supply_chain.ena_requisition_details.views import RequisitionDashboardCountsAPIView
from rest_framework.test import APIRequestFactory, force_authenticate
from django.contrib.auth import get_user_model

User = get_user_model()
for u in User.objects.all()[:5]:
    print(f"User: {u.username}, role: {getattr(getattr(u, 'role', None), 'name', None)}")

qs = EnaRequisitionDetail.objects.all()
print('Total count in DB:', qs.count())
for r in qs:
    stage_name = getattr(r.current_stage, 'name', None) if r.current_stage else None
    print(f"ID: {r.id}, ref: {r.our_ref_no}, status: '{r.status}', stage: '{stage_name}', code: '{r.status_code}', licensee: '{r.licensee_id}'")
