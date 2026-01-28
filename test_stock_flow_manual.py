from django.test import TestCase
from rest_framework.test import APIRequestFactory
from django.contrib.auth import get_user_model
from rest_framework import status

from models.transactional.supply_chain.ena_transit_permit_details.views import PerformTransitPermitActionAPIView
from models.transactional.supply_chain.ena_transit_permit_details.models import EnaTransitPermitDetail
from models.transactional.supply_chain.brand_warehouse.models import BrandWarehouse, BrandWarehouseUtilization

class StockDeductionFlowTest(TestCase):
    def setUp(self):
        # 1. Setup Test Data
        self.brand_name = "TEST_BRAND_V1"
        self.size = 750
        self.initial_stock = 1000
        
        self.warehouse = BrandWarehouse.objects.create(
            distillery_name="Test Distillery",
            brand_type="Whisky",
            brand_details=self.brand_name,
            capacity_size=self.size,
            current_stock=self.initial_stock,
            max_capacity=5000,
            status='IN_STOCK'
        )
        
        # Create User
        User = get_user_model()
        self.user = User.objects.create_superuser('admin_test', 'admin@test.com', 'password')

    def test_stock_deduction_on_pay(self):
        print("\n" + "="*50)
        print("TEST: Stock Deduction on Payment")
        print("="*50)
        
        # 1. Create Transit Permit
        cases = 5
        permit = EnaTransitPermitDetail.objects.create(
            bill_no="TEST-BILL-001",
            sole_distributor_name="Test Distributor",
            date="2024-01-28",
            depot_address="Test Address",
            brand=self.brand_name,
            size_ml=str(self.size),
            cases=cases,
            status="Ready for Payment",
            status_code="TRP_01"
        )
        print(f"[STEP 1] Created Permit {permit.bill_no} for {cases} cases")

        # 2. Check Initial Stock
        self.warehouse.refresh_from_db()
        print(f"[CHECK] Stock BEFORE Payment: {self.warehouse.current_stock}")
        self.assertEqual(self.warehouse.current_stock, self.initial_stock)

        # 3. Perform Payment Action
        print(f"[STEP 2] Performing PAY action...")
        view = PerformTransitPermitActionAPIView()
        factory = APIRequestFactory()
        request = factory.post(f'/action/{permit.id}/', {'action': 'PAY'})
        request.user = self.user
        
        response = view.post(request, pk=permit.id)
        
        print(f"[STEP 2] Response: {response.status_code}")
        
        # 4. Check Stock After Payment
        self.warehouse.refresh_from_db()
        print(f"[CHECK] Stock AFTER Payment: {self.warehouse.current_stock}")
        
        expected_deduction = cases * 12
        expected_stock = self.initial_stock - expected_deduction
        
        print(f"[INFO] Expected Remaining: {expected_stock}")
        
        # Assertions
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.warehouse.current_stock, expected_stock, "Stock should be deducted correctly")
        
        # 5. Check Utilization Record
        util_exists = BrandWarehouseUtilization.objects.filter(permit_no=permit.bill_no).exists()
        print(f"[CHECK] Utilization Record Created: {util_exists}")
        self.assertTrue(util_exists, "Utilization record should be created")

        print("\nTEST COMPLETED SUCCESSFULLY")
