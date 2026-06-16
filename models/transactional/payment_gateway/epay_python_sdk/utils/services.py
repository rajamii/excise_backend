"""
API resource for handling HTTP requests with encryption/decryption.
"""

import requests
import json
from typing import Dict, Any, Optional
from ..types import ResponseEntity
from .crypto.encryption import encrypt_payload
from .crypto.decryption import decrypt_payload
from ..modules.access_token import AccessToken
from .logger import log_sdk_operation
from .constants import log_titles, exceptions
from ..exceptions.SBIEpayException import SBIEpayException

class Services:
    """
    API resource class that handles all interactions with API methods.
    """
    
    def __init__(self, session: requests.Session, encryption_key: str, logging: bool, responseType: str):
        """
        Initialize API with session and encryption key.
        
        Args:
            session: The requests session for making HTTP calls
            encryption_key: The encryption key for payload encryption/decryption
        """
        self.session = session
        self.access_token = AccessToken(session, logging, log_sdk_operation, log_titles)
        self.encryption_key = encryption_key
        self.logging = logging
        self.responseType = responseType
    
    def update_instance(self) -> None:
        """
        Update the session with access token authorization.
        """
        try:
            token_response = self.access_token.get_token()
            if token_response.get("errors"):
                log_sdk_operation(self.logging, log_titles["access_token"], "error", token_response)
                return token_response
                
            if token_response.get("data") and token_response["data"]:
                log_sdk_operation(self.logging, log_titles["access_token"], "success", token_response)
                token = token_response["data"][0]
                self.session.headers.update({
                    'Authorization': f'Bearer {token}'
                })
                # Remove API key headers after getting token
                self.session.headers.pop('Merchant-API-Key-Id', None)
                self.session.headers.pop('Merchant-API-Key-Secret', None)
        except requests.exceptions.SSLError as ssl_err:
            return json.loads(ResponseEntity.error('Something went wrong.', "400").to_json())
        except requests.exceptions.RequestException as req_err:
            return json.loads(ResponseEntity.error('Something went wrong.', "400").to_json())
        except Exception as e:
            return json.loads(ResponseEntity.error('Something went wrong.', "400").to_json())
    
    def _post(self, url: str, action_label: str, payload: Optional[Dict[str, Any]] = None) -> ResponseEntity:
        """POST API Request with proper exception handling."""
        
        if not url:
            raise SBIEpayException(exceptions["io_exception_error_code"], "API url is required")
        
        try:
            # Update instance with access token if not present
            if 'Authorization' not in self.session.headers:
                self.update_instance()  # This will raise SBIEpayException if it fails
            
            # Encrypt payload if provided
            encrypted_payload = {}
            if payload:
                if isinstance(payload, str):
                    encrypted_payload = encrypt_payload(self.encryption_key, json.loads(payload))
                else:
                    encrypted_payload = encrypt_payload(self.encryption_key, payload)
            
            # Make the request
            response = self.session.post(url, json=encrypted_payload)
            response.raise_for_status()
            
            # Process response with proper exception handling
            constant_prefix = action_label.lower().replace(" ", "_")
            decrypted_response = self._process_epay_response(response, action_label, constant_prefix)
            
            return json.loads(ResponseEntity.success(
                data=decrypted_response['data']
            ).to_json())
        except requests.exceptions.ConnectionError as e:
            log_sdk_operation(self.logging, action_label, "error", log_titles["network_error"])
            raise SBIEpayException(exceptions["io_exception_error_code"], log_titles["network_error"], str(e.args[0].reason))
        except requests.exceptions.Timeout as e:
            log_sdk_operation(self.logging, action_label, "error", log_titles["timeout_error"])
            raise SBIEpayException(exceptions["io_exception_error_code"], log_titles["timeout_error"], str(e.args[0]))
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                error_data = e.response.json()
                log_sdk_operation(self.logging, action_label, "error", json.dumps(error_data))
                raise SBIEpayException(e.response.status_code, json.dumps(error_data), e)
            log_sdk_operation(self.logging, action_label, "error", log_titles["request_error"])
            raise SBIEpayException(exceptions["io_exception_error_code"], log_titles["request_error"], e)
        # except Exception as e:
        #     log_sdk_operation(self.logging, action_label, "error", log_titles["unexpected_error"])
        #     raise SBIEpayException(exceptions["io_exception_error_code"], log_titles["unexpected_error"], e)

    def _get(self, url: str, action_label: str) -> ResponseEntity:
        """GET API Request with proper exception handling."""        
        if not url:
            raise SBIEpayException(exceptions["io_exception_error_code"], "API url is required")
        
        try:
            # Update instance with access token if not present
            if 'Authorization' not in self.session.headers:
                self.update_instance()
            
            # Make the request
            # response = self.session.get(url, timeout=0.1) // to test timeout error handling
            response = self.session.get(url)
            response.raise_for_status()
            
            # Process response with proper exception handling
            constant_prefix = action_label.lower().replace(" ", "_")
            decrypted_response = self._process_epay_response(response, action_label, constant_prefix)
            
            return json.loads(ResponseEntity.success(data=decrypted_response['data']).to_json())
        except requests.exceptions.ConnectionError as e:
            log_sdk_operation(self.logging, action_label, "error", log_titles["network_error"])
            raise SBIEpayException(exceptions["io_exception_error_code"], log_titles["network_error"], str(e.args[0].reason))
        except requests.exceptions.Timeout as e:
            log_sdk_operation(self.logging, action_label, "error", log_titles["timeout_error"])
            raise SBIEpayException(exceptions["io_exception_error_code"], log_titles["timeout_error"], str(e.args[0]))
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                error_data = e.response.json()
                log_sdk_operation(self.logging, action_label, "error", json.dumps(error_data))
                raise SBIEpayException(e.response.status_code, json.dumps(error_data), e)
            log_sdk_operation(self.logging, action_label, "error", log_titles["request_error"])
            raise SBIEpayException(exceptions["io_exception_error_code"], log_titles["request_error"], e)
        # except Exception as e:
        #     log_sdk_operation(self.logging, action_label, "error", log_titles["unexpected_error"])
        #     raise SBIEpayException(exceptions["io_exception_error_code"], log_titles["unexpected_error"], e)

    def _process_epay_response(self, response, action_label: str, constant_prefix: str):
        """
        Process ePay API response with proper exception handling.
        
        Args:
            response: HTTP response object
            action_label: Label for logging
            constant_prefix: Prefix for error constants (e.g., 'customer_create')
            
        Returns:
            Decrypted response data
            
        Raises:
            SBIEpayException: If response processing fails
        """
        if response is None:
            log_sdk_operation(self.logging, action_label, "error", "No response received")
            raise SBIEpayException(exceptions["io_exception_error_code"], exceptions["io_exception_error_msg"])
        
        try:
            response_data = response.json()
            status_value = response_data.get('status', response_data.get('Status'))
            
            if response.status_code == 200:
                if int(status_value) == 1:
                    log_sdk_operation(self.logging, action_label, "success", response_data)
                    
                    # Decrypt the response
                    decrypted_response = decrypt_payload(self.encryption_key, {'data': response_data}, self.responseType)
                    return decrypted_response
                else:
                    # Business validation error
                    log_sdk_operation(self.logging, action_label, "error", response_data)
                    error_code = exceptions.get(f"{constant_prefix}_error_code", exceptions["error_response_code"])
                    error_msg = exceptions["invalid_response_error_msg"].format(json.dumps(response_data["errors"]))
                    raise SBIEpayException(error_code, error_msg)
            else:
                # HTTP error
                error_code = exceptions["invalid_response_error_code"]
                error_msg = exceptions["invalid_response_error_msg"].format(json.dumps(response_data))
                raise SBIEpayException(error_code, error_msg)
                
        except json.JSONDecodeError as e:
            log_sdk_operation(self.logging, action_label, "error", log_titles["json_decode_error"])
            raise SBIEpayException(exceptions["json_processing_error_code"], log_titles["json_decode_error"], e)