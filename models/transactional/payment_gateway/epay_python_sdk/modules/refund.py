"""
Refund resource for handling refund-related API operations.
"""

import requests
import json
from ..types import RefundEntity, RefundSearchEntity, ResponseEntity
from ..utils.services import Services
from ..utils.constants import log_titles
from ..exceptions.SBIEpayException import SBIEpayException

class Refund(Services):
    """
    Refund resource class that handles all interactions with the /refund API endpoint.
    """
    
    def __init__(self, session: requests.Session, encryption_key: str, logging: bool, responseType: str):
        """
        Initialize Refund with session and encryption key.
        
        Args:
            session: The requests session for making HTTP calls
            encryption_key: The encryption key for payload encryption/decryption
            logging: The logging argument for showing logs if enabled
        """
        super().__init__(session, encryption_key, logging, responseType)
    
    def book(self, payload: RefundEntity) -> ResponseEntity:
        """
        Book a refund.
        
        Args:
            payload: The data for booking refund
            
        Returns:
            ResponseEntity containing the created refund entity
        """
        try:
            # Convert dataclass to dict
            if hasattr(payload, '__dict__'):
                payload_dict = payload.__dict__
            else:
                payload_dict = payload
            
            refund = self._post('refund/book', log_titles["refund_book"], payload_dict)
            return refund
        except SBIEpayException as e:
            # Convert SBIEpayException to ResponseEntity error format
            error_code = str(e.get_status_code()) if e.get_status_code() else '400'
            return json.loads(ResponseEntity.error(str(e), error_code).to_json())
        except Exception as error:
            return json.loads(ResponseEntity.error(str(error), '400').to_json())
    
    def search(self, payload: RefundSearchEntity, page: int = 0, size: int = 50) -> ResponseEntity:
        """
        Search refunds by search payload.
        
        Args:
            payload: The search payload of the refund
            page: Page number for pagination (default: 0)
            size: Number of records per page (default: 50)
            
        Returns:
            ResponseEntity containing the fetched refund entity
        """
        try:
            # Convert dataclass to dict
            if hasattr(payload, '__dict__'):
                payload_dict = payload.__dict__
            else:
                payload_dict = payload
            
            refund = self._post(f'refund/search?page={page}&size={size}', log_titles["refund_search"], payload_dict)
            return refund
        except SBIEpayException as e:
            # Convert SBIEpayException to ResponseEntity error format
            error_code = str(e.get_status_code()) if e.get_status_code() else '400'
            return json.loads(ResponseEntity.error(str(e), error_code).to_json())
        except Exception as error:
            return json.loads(ResponseEntity.error(str(error), '400').to_json())