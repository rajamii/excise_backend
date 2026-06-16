"""
Main SDK entry point.
This file exports the main SDK class that users will instantiate.
"""

import requests
import certifi
import json
from .config import ENVIRONMENTS
from .types import SDKCredentials, Environment
from .modules.customer import Customer
from .modules.order import Order
from .modules.refund import Refund
from .modules.crypto import Crypto
from .utils.logger import log_sdk_operation
from .utils.constants import errors, exceptions, log_titles
from .exceptions.SBIEpayException import SBIEpayException

class SBIEPayClient:
    """
    The main class for the SBI ePay SDK.
    Users will instantiate this class to interact with the API.
    """
    
    def __init__(self, credentials: SDKCredentials, environment: Environment, **kwargs):
        """
        Create an instance of the SBIEPayClient SDK.
        Pass logging as a keyword argument, so it is caught by **kwargs since it is optional
        
        Args:
            credentials: The credentials for the SDK
            environment: LIVE or SANDBOX
            logging: True or False (optional, default False)
            responseType: JSON or STRING (optional, default JSON)
            
        Raises:
            SBIEpayException: If required credentials are missing
            SBIEpayException: If required environment key is missing or not passed correctly
            SBIEpayException: If logging parameter is not boolean
            SBIEpayException: If responseType parameter is missing
        """
        
        # Extract logging parameter
        logging = kwargs.get('logging', False)
        # Extract responseType parameter
        responseType = kwargs.get('responseType', 'JSON')
        
        # Validate credentials
        if not credentials.api_key or not credentials.api_secret:
            log_sdk_operation(
                logging,
                log_titles["sbi_epay_client_initialization_error"],
                "error",
                errors["credentials_error"]
            )
            error_data = {"error": errors["credentials_error"]}
            raise SBIEpayException(
                exceptions["error_response_code"],
                f'{exceptions["invalid_response_error_msg"].format(json.dumps(error_data))}'
            )
        # Validate credentials
        if not credentials.encryption_key:
            log_sdk_operation(
                logging,
                log_titles["sbi_epay_client_initialization_error"],
                "error",
                errors["encryption_key_error"]
            )
            error_data = {"error": errors["encryption_key_error"]}
            raise SBIEpayException(
                exceptions["error_response_code"],
                f'{exceptions["invalid_response_error_msg"].format(json.dumps(error_data))}'
            )
        
        # Validate environment
        if not environment or environment not in ["LIVE", "SANDBOX"]:
            log_sdk_operation(
                logging,
                log_titles["sbi_epay_client_initialization_error"],
                "error",
                errors["environment_error"]
            )
            error_data = {"error": errors["environment_error"]}
            raise SBIEpayException(
                exceptions["error_response_code"],
                f'{exceptions["invalid_response_error_msg"].format(json.dumps(error_data))}'
            )
        
        # Validate logging parameter
        if not isinstance(logging, bool):
            log_sdk_operation(
                logging,  # Don't log this with potentially invalid logging parameter
                log_titles["sbi_epay_client_initialization_error"],
                "error",
                errors["logging_error"]
            )
            error_data = {"error": errors["logging_error"]}
            raise SBIEpayException(
                exceptions["error_response_code"],
                f'{exceptions["invalid_response_error_msg"].format(json.dumps(error_data))}'
            )
        
        # Log successful initialization parameters
        log_sdk_operation(logging, "Environment", "info", environment)
        log_sdk_operation(logging, "Logging", "info", logging)
        log_sdk_operation(logging, "Response Type", "info", responseType)
        
        # Create requests session
        self.session = requests.Session()
        self.session.verify = certifi.where()
        self.session.verify = False  # Note: In production, consider setting this to True
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Merchant-API-Key-Id': credentials.api_key,
            'Merchant-API-Key-Secret': credentials.api_secret
        })
        
        # Set base URL based on environment
        if environment == "LIVE":
            base_url = ENVIRONMENTS["LIVE_API_BASE_URL"]
        else:
            base_url = ENVIRONMENTS["SANDBOX_API_BASE_URL"]
        
        self.session.base_url = f"{base_url}"
        
        # Override request method to use base URL
        original_request = self.session.request
        
        def request_with_base_url(method, url, **kwargs):
            if not url.startswith('http'):
                url = self.session.base_url + url
            return original_request(method, url, **kwargs)
        
        self.session.request = request_with_base_url
        
        # Initialize modules
        self.customer = Customer(self.session, credentials.encryption_key, logging, responseType)
        self.order = Order(self.session, credentials.encryption_key, logging, responseType)
        self.refund = Refund(self.session, credentials.encryption_key, logging, responseType)
        self.crypto = Crypto(credentials.encryption_key, logging, responseType)