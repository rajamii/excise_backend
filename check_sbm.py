import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from models.transactional.salesman_barman.models import SalesmanBarmanModel
from models.transactional.salesman_barman.serializers import SalesmanBarmanSerializer

apps = SalesmanBarmanModel.objects.all()
print(f"Total SBM applications: {apps.count()}")
print()
for app in apps:
    ser = SalesmanBarmanSerializer(app)
    d = ser.data
    nli = d.get("new_license_application_id")
    lic = getattr(app, "license_id", None)
    parent_paid = d.get("is_parent_license_fee_paid")
    stage = d.get("current_stage_name")
    print(f"{app.application_id}: nli={nli}, license={lic}, is_parent_paid={parent_paid}, stage={stage}")
