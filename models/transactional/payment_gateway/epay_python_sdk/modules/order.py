"""
Order resource for handling order-related API operations.
"""

import requests
import json
from ..types import OrderEntity, OrderSearchEntity, ResponseEntity
from ..utils.services import Services
from ..utils.constants import log_titles
from ..exceptions.SBIEpayException import SBIEpayException

class Order(Services):
    """
    Order resource class that handles all interactions with the /order API endpoint.
    """
    
    def __init__(self, session: requests.Session, encryption_key: str, logging: bool, responseType: str):
        """
        Initialize Order with session and encryption key.
        
        Args:
            session: The requests session for making HTTP calls
            encryption_key: The encryption key for payload encryption/decryption
            logging: The logging argument for showing logs if enabled
        """
        super().__init__(session, encryption_key, logging, responseType)
    
    def create(self, payload: OrderEntity) -> ResponseEntity:
        """
        Create a new order.
        
        Args:
            payload: The data for creating the order
            
        Returns:
            ResponseEntity containing the created order entity
        """
        try:
            # Convert dataclass to dict
            if hasattr(payload, '__dict__'):
                payload_dict = payload.__dict__
            else:
                payload_dict = payload
            
            order = self._post('order/create', log_titles["order_create"], payload_dict)
            return order
        except SBIEpayException as e:
            # Convert SBIEpayException to ResponseEntity error format
            error_code = str(e.get_status_code()) if e.get_status_code() else '400'
            return json.loads(ResponseEntity.error(str(e), error_code).to_json())
        except Exception as error:
            return json.loads(ResponseEntity.error(str(error), '400').to_json())
    
    def search(self, payload: OrderSearchEntity) -> ResponseEntity:
        """
        Search orders by search payload.
        
        Args:
            payload: The search payload of the order
            
        Returns:
            ResponseEntity containing the fetched order entity
        """
        try:
            # Convert dataclass to dict
            if hasattr(payload, '__dict__'):
                payload_dict = payload.__dict__
            else:
                payload_dict = payload
            
            order = self._post('order/status', log_titles["order_search"], payload_dict)
            return order
        except SBIEpayException as e:
            # Convert SBIEpayException to ResponseEntity error format
            error_code = str(e.get_status_code()) if e.get_status_code() else '400'
            return json.loads(ResponseEntity.error(str(e), error_code).to_json())
        except Exception as error:
            return json.loads(ResponseEntity.error(str(error), '400').to_json())