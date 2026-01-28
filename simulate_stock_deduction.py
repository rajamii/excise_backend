import os
import django
import sys

# Setup Django environment
sys.path.append('f:\\new_excise\\excise_backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from rest_framework.test import APIRequestFactory
from models.transactional.supply_chain.ena_transit_permit_details.views import PerformTransitPermitActionAPIView
from models.transactional.supply_chain.ena_transit_permit_details.models import EnaTransitPermitDetail
from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouse
from django.contrib.auth import get_user_model
from rest_framework import status

def run_test():
    print("="*50)
    print("STARTING STOCK DEDUCTION TEST")
    print("="*50)

    # 1. Setup Test Data (Brand Warehouse)
    brand_name = "TEST_BRAND_V1"
    size = 750
    initial_stock = 1000
    
    # Clean up old test data specifically for this run
    BrandWarehouse.objects.filter(brand_details=brand_name).delete()
    EnaTransitPermitDetail.objects.filter(bill_no="TEST-BILL-001").delete()

    print(f"\n[SETUP] Creating Brand: {brand_name}, Size: {size}, Stock: {initial_stock}")
    warehouse = BrandWarehouse.objects.create(
        distillery_name="Test Distillery",
        brand_type="Whisky",
        brand_details=brand_name,
        capacity_size=size,
        current_stock=initial_stock,
        max_capacity=5000,
        status='IN_STOCK'
    )
    print(f"[SETUP] Warehouse ID: {warehouse.id} created.")

    # 2. Creating Transit Permit Application (Simulate Submit)
    cases = 5
    print(f"\n[STEP 1] submitting Transit Permit for {cases} cases.")
    
    permit = EnaTransitPermitDetail.objects.create(
        bill_no="TEST-BILL-001",
        sole_distributor_name="Test Distributor",
        date="2024-01-28",
        depot_address="Test Address",
        brand=brand_name,
        size_ml=str(size),
        cases=cases,
        status="Ready for Payment",
        status_code="TRP_01"
    )
    print(f"[STEP 1] Permit ID: {permit.id} created with Status: {permit.status}")

    # 3. Verify Stock Before Payment
    warehouse.refresh_from_db()
    print(f"\n[CHECK] Stock BEFORE Payment: {warehouse.current_stock}")
    if warehouse.current_stock != initial_stock:
        print("!!! ERROR: Stock changed before payment!")
        return

    # 4. Perform Payment Action
    print(f"\n[STEP 2] Performing Payment Action (PAY)...")
    
    view = PerformTransitPermitActionAPIView()
    factory = APIRequestFactory()
    
    from rest_framework.request import Request as DRFRequest
    from rest_framework.parsers import JSONParser
    from auth.roles.models import Role # Adjusted import path based on findings

    # Mock request - Use json format explicitly
    request = factory.post(f'/action/{permit.id}/', {'action': 'PAY'}, format='json')
    
    # Mock user 
    User = get_user_model()
    try:
        user = User.objects.get(username='admin')
    except User.DoesNotExist:
        user = User.objects.create_superuser('admin', 'admin@test.com', 'password')
    
    # Ensure user has a role
    role, _ = Role.objects.get_or_create(name='Super Admin Test', defaults={'role_precedence': 100})
    user.role = role
    user.save() # Save just in case logic queries DB, though here we attach to object

    request.user = user

    # Wrap in DRF Request to provide .data attribute
    drf_request = DRFRequest(request, parsers=[JSONParser()])
    drf_request._user = user  # Force user to avoid authentication
    drf_request._auth = None

    # Execute View
    response = view.post(drf_request, pk=permit.id)
    
    print(f"[STEP 2] Response Status: {response.status_code}")
    print(f"[STEP 2] Response Data: {response.data}")

    # 5. Verify Stock After Payment
    warehouse.refresh_from_db()
    print(f"\n[CHECK] Stock AFTER Payment: {warehouse.current_stock}")
    
    # Calculate Expected Deduction
    # Logic in view defaults to: 750ml = 12 bottles/case
    expected_deduction = cases * 12 
    expected_stock = initial_stock - expected_deduction
    
    print(f"[INFO] Expected Deduction: {expected_deduction} pieces ({cases} cases * 12)")
    print(f"[INFO] Expected Remaining: {expected_stock}")

    if warehouse.current_stock == expected_stock:
        print("\nSUCCESS: Stock was deducted correctly!")
    else:
        print(f"\nFAILURE: Stock mismatch! Expected {expected_stock}, got {warehouse.current_stock}")

    # 6. Verify Utilization Record
    if response.status_code == 200:
        # Using model queries
        from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouseUtilization
        utils = BrandWarehouseUtilization.objects.filter(permit_no=permit.bill_no)
        print(f"\n[CHECK] Utilization Records found: {utils.count()}")
        for u in utils:
            print(f" - Utilization: {u.quantity} pieces, Status: {u.status}")

if __name__ == "__main__":
    run_test()
