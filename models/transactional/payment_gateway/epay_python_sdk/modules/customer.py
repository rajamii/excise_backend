"""
Customer resource for handling customer-related API operations.
"""

import requests
import json
from typing import Literal
from ..types import CustomerEntity, ResponseEntity
from ..utils.services import Services
from ..utils.constants import log_titles, status, exceptions
from ..exceptions.SBIEpayException import SBIEpayException

class Customer(Services):
    """
    Customer resource class that handles all interactions with the /customer API endpoint.
    """
    def __init__(self, session: requests.Session, encryption_key: str, logging: bool, responseType: str):
        """
        Initialize Customer with session and encryption key.
        
        Args:
            session: The requests session for making HTTP calls
            encryption_key: The encryption key for payload encryption/decryption
            logging: The logging argument for showing logs if enabled
        """
        super().__init__(session, encryption_key, logging, responseType)
    
    def create(self, payload: CustomerEntity) -> ResponseEntity:
        """
        Create a new customer.
        
        Args:
            payload: The data for creating the customer
            
        Returns:
            ResponseEntity containing the created customer entity
        """
        try:
            if not payload:
                # Format error message like API response
                error_response = [{
                    "errorCode": exceptions["customer_payload_required"],
                    "errorMessage": "Customer payload is required."
                }]
                raise SBIEpayException(
                    exceptions["error_response_code"],
                    exceptions["invalid_response_error_msg"].format(json.dumps(error_response))
                )
            
            if hasattr(payload, '__dict__'):
                payload_dict = payload.__dict__
            else:
                payload_dict = payload
            
            customer = self._post('customer/create', log_titles["customer_create"], payload_dict)
            return customer
        except SBIEpayException as e:
            # Convert SBIEpayException to ResponseEntity error format
            error_code = str(e.get_status_code()) if e.get_status_code() else '400'
            return json.loads(ResponseEntity.error(str(e), error_code).to_json())
        except Exception as error:
            return json.loads(ResponseEntity.error(str(error), '400').to_json())
    
    def get(self, customer_id: str) -> ResponseEntity:
        """
        Get a specific customer by its ID.
        
        Args:
            customer_id: The unique identifier of the customer
            
        Returns:
            ResponseEntity containing the fetched customer entity  
        """
        try:
            if not customer_id or not customer_id.strip():
                # Format error message like API response
                error_response = [{
                    "errorCode": exceptions["customer_id_required"],
                    "errorMessage": "Customer ID is required."
                }]
                raise SBIEpayException(
                    exceptions["error_response_code"],
                    exceptions["invalid_response_error_msg"].format(json.dumps(error_response))
                )
        
            customer = self._get(f'customer/{customer_id}', log_titles["customer_fetch"])
            return customer
        except SBIEpayException as e:
            error_code = str(e.get_status_code()) if e.get_status_code() else '400'
            return json.loads(ResponseEntity.error(str(e), error_code).to_json())
        except Exception as error:
            return json.loads(ResponseEntity.error(str(error), '400').to_json())

    def __update_status(self, customer_id: str, status: Literal['ACTIVE', 'INACTIVE', 'DELETE']) -> ResponseEntity:
        """
        Update status of a specific customer by its ID.
        
        Args:
            customer_id: The unique identifier of the customer
            status: The status of the customer
            
        Returns:
            ResponseEntity containing the updated customer entity
        """
        try:
            if not customer_id or not customer_id.strip():
                error_response = [{
                    "errorCode": "2001",
                    "errorMessage": "Customer ID is required."
                }]
                raise SBIEpayException(
                    exceptions["error_response_code"],
                    exceptions["invalid_response_error_msg"].format(json.dumps(error_response))
                )
            if not status:
                error_response = [{
                    "errorCode": "2002",
                    "errorMessage": "Customer status is required."
                }]
                raise SBIEpayException(
                    exceptions["error_response_code"],
                    f'SBI EPay Business Validation Errors : {json.dumps(error_response)}'
                )
            customer = self._post(f'customer/{customer_id}/{status}', log_titles["customer_update"])
            return customer
        except SBIEpayException as e:
            error_code = str(e.get_status_code()) if e.get_status_code() else '400'
            return json.loads(ResponseEntity.error(str(e), error_code).to_json())
        except Exception as error:
            return json.loads(ResponseEntity.error(str(error), '400').to_json())
            
    def active(self, customer_id: str) -> ResponseEntity:
        """
        Update status of a specific customer by its ID to ACTIVE.
        
        Args:
            customer_id: The unique identifier of the customer
            
        Returns:
            ResponseEntity containing the updated customer entity
        """
        try:
            if not customer_id or not customer_id.strip():
                error_response = [{
                    "errorCode": "2001",
                    "errorMessage": "Customer ID is required."
                }]
                raise SBIEpayException(
                    exceptions["error_response_code"],
                    exceptions["invalid_response_error_msg"].format(json.dumps(error_response))
                )
            customer = self.__update_status(customer_id, status["active"])
            return customer
        except SBIEpayException as e:
            error_code = str(e.get_status_code()) if e.get_status_code() else '400'
            return json.loads(ResponseEntity.error(str(e), error_code).to_json())
        except Exception as error:
            return json.loads(ResponseEntity.error(str(error), '400').to_json())

    def inactive(self, customer_id: str) -> ResponseEntity:
        """
        Update status of a specific customer by its ID to INACTIVE.
        
        Args:
            customer_id: The unique identifier of the customer
            
        Returns:
            ResponseEntity containing the updated customer entity
        """
        try:
            if not customer_id or not customer_id.strip():
                error_response = [{
                    "errorCode": "2001",
                    "errorMessage": "Customer ID is required."
                }]
                raise SBIEpayException(
                    exceptions["error_response_code"],
                    exceptions["invalid_response_error_msg"].format(json.dumps(error_response))
                )
            customer = self.__update_status(customer_id, status["inactive"])
            return customer
        except SBIEpayException as e:
            error_code = str(e.get_status_code()) if e.get_status_code() else '400'
            return json.loads(ResponseEntity.error(str(e), error_code).to_json())
        except Exception as error:
            return ResponseEntity.error(str(error)).to_json()

    def delete(self, customer_id: str) -> ResponseEntity:
        """
        Update status of a specific customer by its ID to DELETE.
        
        Args:
            customer_id: The unique identifier of the customer
            
        Returns:
            ResponseEntity containing the updated customer entity
        """
        try:
            if not customer_id or not customer_id.strip():
                error_response = [{
                    "errorCode": "2001",
                    "errorMessage": "Customer ID is required."
                }]
                raise SBIEpayException(
                    exceptions["error_response_code"],
                    exceptions["invalid_response_error_msg"].format(json.dumps(error_response))
                )
            customer = self.__update_status(customer_id, status["delete"])
            return customer
        except SBIEpayException as e:
            error_code = str(e.get_status_code()) if e.get_status_code() else '400'
            return json.loads(ResponseEntity.error(str(e), error_code).to_json())
        except Exception as error:
            return ResponseEntity.error(str(error)).to_json()