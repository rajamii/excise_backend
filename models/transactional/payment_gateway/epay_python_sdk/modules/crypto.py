"""
Crypto resource.
This class handles all interactions with crypto operations for encryption/decryption.
"""

import json
import base64
from typing import Any, Union
from ..utils.crypto.aes import encrypt, decrypt
from ..utils.logger import log_sdk_operation
from ..utils.constants import errors, exceptions, log_titles
from ..exceptions.SBIEpayException import SBIEpayException


class Crypto:
    """
    Crypto resource class that handles encryption, decryption, and callback decoding.
    """
    
    def __init__(self, encryption_key: str, logging: bool, response_type: str = "JSON"):
        """
        Initialize Crypto with encryption key and configuration.
        
        Args:
            encryption_key: Encryption key for handling request/response encryption/decryption
            logging: Enable/Disable API logs
            response_type: Data convert to JSON/STRING enable/disable (default: "JSON")
        """
        self.encryption_key = encryption_key
        self.logging = logging
        self.response_type = response_type.upper()
    
    def encrypt(self, payload: Any) -> str:
        """
        Encrypt payload.
        
        Args:
            payload: The data for encryption
            
        Returns:
            Encrypted payload string
            
        Raises:
            SBIEpayException: If payload is missing or encryption fails
        """
        if not payload:
            log_sdk_operation(self.logging, log_titles["payload_encrypt"], "error", errors["payload_encrypt_error"])
            error_data = {"error": errors["payload_encrypt_error"]}
            raise SBIEpayException(
                exceptions["error_response_code"],
                exceptions["invalid_response_error_msg"].format(json.dumps(error_data))
            )
        
        try:
            # Convert payload to string if it's not already
            payload_str = payload if isinstance(payload, str) else json.dumps(payload)
            
            # Encrypt the payload
            encrypted_payload = encrypt(self.encryption_key, payload_str)
            
            log_sdk_operation(self.logging, log_titles["payload_encrypt"], "success", encrypted_payload)
            
            return encrypted_payload
            
        except SBIEpayException:
            raise
        except Exception as error:
            log_sdk_operation(self.logging, log_titles["payload_encrypt"], "error", str(error))
            
            # Format error data
            if hasattr(error, 'args') and error.args:
                error_data = [{"errorCode": "400", "errorMessage": str(error)}]
            else:
                error_data = [{"errorCode": "500", "errorMessage": errors["api_error"]}]
            
            # Get exception details if available
            exception_code = getattr(error, 'exceptionCode', exceptions["invalid_response_error_code"])
            exception_message = getattr(error, 'exceptionMessage', exceptions["invalid_response_error_msg"])
            
            raise SBIEpayException(
                exception_code,
                exception_message.format(json.dumps(error_data)) if "{0}" in str(exception_message) else str(exception_message)
            )
    
    def decrypt(self, payload: str) -> Union[str, dict]:
        """
        Decrypt payload.
        
        Args:
            payload: The encrypted data for decryption
            
        Returns:
            Decrypted payload (string or dict based on response_type)
            
        Raises:
            SBIEpayException: If payload is missing or decryption fails
        """
        if not payload:
            log_sdk_operation(self.logging, log_titles["payload_decrypt"], "error", errors["payload_decrypt_error"])
            error_data = {"error": errors["payload_decrypt_error"]}
            raise SBIEpayException(
                exceptions["error_response_code"],
                exceptions["invalid_response_error_msg"].format(json.dumps(error_data))
            )
        
        try:
            # Decrypt the payload
            decrypted_payload = decrypt(self.encryption_key, payload)
            
            log_sdk_operation(self.logging, log_titles["payload_decrypt"], "success", decrypted_payload)
            
            # Return based on response type
            if self.response_type == "STRING":
                return decrypted_payload
            else:
                return json.loads(decrypted_payload)
            
        except SBIEpayException:
            raise
        except json.JSONDecodeError as error:
            log_sdk_operation(self.logging, log_titles["payload_decrypt"], "error", f"JSON decode error: {str(error)}")
            error_data = [{"errorCode": "400", "errorMessage": f"Invalid JSON format: {str(error)}"}]
            raise SBIEpayException(
                exceptions["json_processing_error_code"],
                exceptions["invalid_response_error_msg"].format(json.dumps(error_data))
            )
        except Exception as error:
            log_sdk_operation(self.logging, log_titles["payload_decrypt"], "error", str(error))
            
            # Format error data
            if hasattr(error, 'args') and error.args:
                error_data = [{"errorCode": "400", "errorMessage": str(error)}]
            else:
                error_data = [{"errorCode": "500", "errorMessage": errors["api_error"]}]
            
            # Get exception details if available
            exception_code = getattr(error, 'exceptionCode', exceptions["invalid_response_error_code"])
            exception_message = getattr(error, 'exceptionMessage', exceptions["invalid_response_error_msg"])
            
            raise SBIEpayException(
                exception_code,
                exception_message.format(json.dumps(error_data)) if "{0}" in str(exception_message) else str(exception_message)
            )
    
    def decodeCallback(self, payload: str) -> Union[str, dict]:
        """
        Decode callback payload (Base64 + URI decode + decrypt).
        
        Args:
            payload: The encoded callback data for decoding
            
        Returns:
            Decoded payload (string or dict based on response_type)
            
        Raises:
            SBIEpayException: If payload is missing or decoding fails
        """
        if not payload:
            log_sdk_operation(self.logging, log_titles["decode_callback"], "error", errors["decode_callback_error"])
            error_data = {"error": errors["decode_callback_error"]}
            raise SBIEpayException(
                exceptions["error_response_code"],
                exceptions["invalid_response_error_msg"].format(json.dumps(error_data))
            )
        
        try:
            # URL decode and Base64 decode
            from urllib.parse import unquote
            
            # First URL decode
            uri_decoded = unquote(payload)
            
            # Then Base64 decode
            uri_base64_decoded = base64.b64decode(uri_decoded).decode('utf-8')
            
            # Remove quotes if present
            uri_base64_decoded = uri_base64_decoded.replace('"', '')
            
            # Decrypt the payload
            decrypted_payload = decrypt(self.encryption_key, uri_base64_decoded)
            
            log_sdk_operation(self.logging, log_titles["decode_callback"], "success", decrypted_payload)
            
            # Return based on response type
            if self.response_type == "STRING":
                return decrypted_payload
            else:
                return json.loads(decrypted_payload)
            
        except SBIEpayException:
            raise
        except json.JSONDecodeError as error:
            log_sdk_operation(self.logging, log_titles["decode_callback"], "error", f"JSON decode error: {str(error)}")
            error_data = [{"errorCode": "400", "errorMessage": f"Invalid JSON format: {str(error)}"}]
            raise SBIEpayException(
                exceptions["json_processing_error_code"],
                exceptions["invalid_response_error_msg"].format(json.dumps(error_data))
            )
        except Exception as error:
            log_sdk_operation(self.logging, log_titles["decode_callback"], "error", str(error))
            
            # Format error data
            if hasattr(error, 'args') and error.args:
                error_data = [{"errorCode": "400", "errorMessage": str(error)}]
            else:
                error_data = [{"errorCode": "500", "errorMessage": errors["api_error"]}]
            
            # Get exception details if available
            exception_code = getattr(error, 'exceptionCode', exceptions["invalid_response_error_code"])
            exception_message = getattr(error, 'exceptionMessage', exceptions["invalid_response_error_msg"])
            
            raise SBIEpayException(
                exception_code,
                exception_message.format(json.dumps(error_data)) if "{0}" in str(exception_message) else str(exception_message)
            )