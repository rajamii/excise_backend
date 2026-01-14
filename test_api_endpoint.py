import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from django.test import RequestFactory
from django.contrib.auth import get_user_model
from models.transactional.supply_chain.hologram.views import HologramRollsDetailsViewSet
from models.masters.supply_chain.profile.models import SupplyChainUserProfile
from auth.roles.models import Role

User = get_user_model()

# Create a test request
factory = RequestFactory()
request = factory.get('/api/rolls-details/')

# Get or create a test user with OIC role
try:
    role = Role.objects.get(name='officer_in_charge')
except:
    role = Role.objects.create(name='officer_in_charge', description='Officer In Charge')

try:
    user = User.objects.get(username='test_oic')
except:
    user = User.objects.create_user(username='test_oic', password='test123')
    user.role = role
    user.save()

# Create supply chain profile if needed
try:
    profile = SupplyChainUserProfile.objects.get(user=user)
except:
    profile = SupplyChainUserProfile.objects.create(
        user=user,
        manufacturing_unit_name='Test Unit'
    )
    user.supply_chain_profile = profile
    user.save()

request.user = user

# Call the viewset
viewset = HologramRollsDetailsViewSet.as_view({'get': 'list'})
response = viewset(request)

print("=" * 80)
print("API ENDPOINT TEST")
print("=" * 80)
print(f"Status Code: {response.status_code}")
print(f"\nResponse Data:")
print(json.dumps(response.data, indent=2))
