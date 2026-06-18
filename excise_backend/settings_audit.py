from .settings import *

# Override the database name for the audit instance
DATABASES['default']['NAME'] = 'eAbkari_db'

# Override payment gateway receipt URLs for the audit environment
PAYMENT_GATEWAY_FRONTEND_SUCCESS_URL = "https://sems.sikkim.gov.in:8443/dashboard/wallet-recharge/success"
PAYMENT_GATEWAY_FRONTEND_NEW_LICENSE_RECEIPT_URL = "https://sems.sikkim.gov.in:8443/dashboard/new-license/application-fee/receipt"