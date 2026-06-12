"""
Access token module with retry mechanism for token requests only.
"""

import requests
import json
import time
from typing import Optional, Any
from ..types import ResponseEntity

class TokenRetryConfig:
    """Configuration for access token retry mechanism."""
    
    def __init__(
        self,
        max_retries: int = 2,
        backoff_factor: float = 0.5,
        status_forcelist: tuple = (500, 502, 503, 504, 429),
        retry_on_timeout: bool = True,
        retry_on_connection_error: bool = True
    ):
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.status_forcelist = status_forcelist
        self.retry_on_timeout = retry_on_timeout
        self.retry_on_connection_error = retry_on_connection_error

class AccessToken:
    """
    Access token management with retry mechanism.
    """
    
    def __init__(self, session: requests.Session, logging: bool, log_sdk_operation: Any, log_titles: Any, retry_config: Optional[TokenRetryConfig] = None):
        """
        Initialize AccessToken with session and optional retry configuration.
        
        Args:
            session: The requests session for making HTTP calls
            retry_config: Configuration for retry mechanism (optional)
        """
        self.session = session
        self.logging = logging
        self.log_sdk_operation = log_sdk_operation
        self.log_titles = log_titles
        self.retry_config = retry_config or TokenRetryConfig()
    
    def _should_retry(self, exception: Exception, attempt: int) -> bool:
        """
        Determine if the token request should be retried.
        
        Args:
            exception: The exception that occurred
            attempt: Current attempt number (0-based)
            
        Returns:
            True if should retry, False otherwise
        """
        if attempt >= self.retry_config.max_retries:
            return False
        
        if isinstance(exception, requests.exceptions.HTTPError):
            if hasattr(exception, 'response') and exception.response is not None:
                return exception.response.status_code in self.retry_config.status_forcelist
        
        if isinstance(exception, requests.exceptions.Timeout):
            return self.retry_config.retry_on_timeout
        
        if isinstance(exception, (requests.exceptions.ConnectionError, requests.exceptions.ConnectTimeout)):
            return self.retry_config.retry_on_connection_error
        
        return False
    
    def _calculate_wait_time(self, attempt: int) -> float:
        """
        Calculate wait time before retry using exponential backoff.
        
        Args:
            attempt: Current attempt number (0-based)
            
        Returns:
            Wait time in seconds
        """
        return self.retry_config.backoff_factor * (2 ** attempt)
    
    def get_token(self) -> ResponseEntity:
        """
        Get access token with retry mechanism.
        
        Returns:
            ResponseEntity containing the access token
            
        Raises:
            SBIEpayException: If token request fails after all retries
        """
        from ..exceptions.SBIEpayException import SBIEpayException
        from ..utils.constants import exceptions

        last_exception = None
        
        for attempt in range(self.retry_config.max_retries + 1):
            try:
                response = self.session.post('token/access')
                response.raise_for_status()
                token_data = response.json()
                
                # Check if response is valid
                if not token_data or not isinstance(token_data, dict):
                    raise SBIEpayException(
                        exceptions["io_exception_error_code"],
                        exceptions["exception_while_calling_access_token_api"]
                    )
                
                status_value = token_data.get('status', token_data.get('Status'))
                
                if response.status_code == 200:
                    if int(status_value) == 1:
                        return token_data
                    else:
                        # Log and raise validation error
                        self.log_sdk_operation(
                            self.logging,
                            self.log_titles["access_token"],
                            "error",
                            token_data
                        )
                        raise SBIEpayException(
                            exceptions["error_response_code"],
                            exceptions["invalid_response_error_msg"].format(json.dumps(token_data))
                        )
                else:
                    raise SBIEpayException(
                        exceptions["invalid_response_error_code"],
                        exceptions["invalid_response_error_msg"].format(json.dumps(token_data))
                    )
                    
            except SBIEpayException:
                raise
            except Exception as e:
                last_exception = e
                
                if not self._should_retry(e, attempt):
                    break
                
                if attempt < self.retry_config.max_retries:
                    wait_time = self._calculate_wait_time(attempt)
                    retryMsg = (
                        f"Token request failed (attempt {attempt + 1}/{self.retry_config.max_retries}). "
                        f"Retrying in {wait_time:.2f} seconds..."
                    )
                    self.log_sdk_operation(self.logging, self.log_titles["access_token"], "error", retryMsg)
                    time.sleep(wait_time)
        
        # If we get here, all retries failed
        raise SBIEpayException(
            exceptions["io_exception_error_code"],
            exceptions["exception_while_calling_access_token_api"],
            last_exception
        )