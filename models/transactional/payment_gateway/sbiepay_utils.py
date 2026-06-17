from .models import PaymentGatewayParameters
from .epay_python_sdk.SBIEPayClient import SBIEPayClient
from .epay_python_sdk.types import SDKCredentials

def get_sbiepay_client():
    gateway = PaymentGatewayParameters.objects.filter(is_active=True, payment_gateway_name__iexact="SBIePay").first()
    if not gateway:
        raise ValueError("SBIePay configuration not found.")

    creds = SDKCredentials(
        api_key=str(gateway.merchantid).strip(),
        api_secret=str(gateway.securityid).strip(),
        encryption_key=str(gateway.encryption_key).strip()
    )
    
    return SBIEPayClient(credentials=creds, environment="SANDBOX", logging=True, responseType="JSON")