
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'excise_backend.settings')
django.setup()

from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework import status
from django.contrib.auth import get_user_model
from models.transactional.supply_chain.ena_cancellation_details.views import EnaCancellationDetailViewSet
from models.transactional.supply_chain.ena_requisition_details.models import EnaRequisitionDetail
from models.masters.supply_chain.status_master.models import StatusMaster

User = get_user_model()

from django.utils import timezone

def test_cancellation_submission():
    print("Setting up test data...")
    # Delete old test data
    EnaRequisitionDetail.objects.filter(our_ref_no='TEST-REQ-001').delete()
    
    # Ensure Requisition Exists
    ref_no = 'TEST-REQ-001'
    req, created = EnaRequisitionDetail.objects.get_or_create(
        our_ref_no=ref_no,
        defaults={
            'requisiton_number_of_permits': 5,
            'requisition_date': timezone.now(),
            'lifted_from_distillery_name': 'Test Distillery',
            'branch_purpose': 'Testing',
            'via_route': 'Route 66',
            'grain_ena_number': 5000.00,
            'totalbl': 5000.00,
            'approval_date': timezone.now(),
            'lifted_from': 'Warehouse 1',
            'purpose_name': 'Manufacturing',
            'check_post_name': 'Checkpost A',
            'state': 'Sikkim',
            'status': 'Approved',
            'status_code': 'RQ_09'
        }
    )
    print(f"Requisition: {req.our_ref_no} (Created: {created})")

    # Create Mock Request
    factory = APIRequestFactory()
    payload = {
        'referenceNo': ref_no,
        'permitNumbers': ['1', '3'],
        'licenseeId': 'LIC-TEST'
    }
    request = factory.post('/api/ena-cancellation-details/submit/', payload, format='json')
    
    # Mock User
    user, _ = User.objects.get_or_create(username='testadmin')
    force_authenticate(request, user=user)

    # Instantiate View
    view = EnaCancellationDetailViewSet.as_view({'post': 'submit_cancellation'})
    
    print("Invoking view...")
    response = view(request)
    
    print(f"Response Status: {response.status_code}")
    print(f"Response Data: {response.data}")

    if response.status_code == status.HTTP_201_CREATED:
        print("SUCCESS! Verification of DB record:")
        from models.transactional.supply_chain.ena_cancellation_details.models import EnaCancellationDetail
        cancel_obj = EnaCancellationDetail.objects.get(id=response.data['id'])
        print(f"  - Ref No: {cancel_obj.our_ref_no}")
        print(f"  - Cancelled Permits: {cancel_obj.cancelled_permit_number}")
        print(f"  - Total Amount: {cancel_obj.total_cancellation_amount} (Expected: 2000.00)")
        print(f"  - Status: {cancel_obj.status}")
        
        if cancel_obj.total_cancellation_amount == 2000.00 and cancel_obj.cancelled_permit_number == "1,3":
             print("VERIFICATION PASSED")
        else:
             print("VERIFICATION FAILED: Data mismatch")
    else:
        print("VERIFICATION FAILED: API Error")

if __name__ == '__main__':
    test_cancellation_submission()
