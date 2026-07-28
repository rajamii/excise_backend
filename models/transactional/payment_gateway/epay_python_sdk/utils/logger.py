import logging
import json
import os
from typing import Any, Dict, Optional, Union
from datetime import datetime

# ANSI escape codes for colors
ERROR = "\033[91m"
INFO = "\033[92m"
WARNING = "\033[93m"
DEBUG = "\033[94m"
CRITICAL = "\033[95m"
RESET = "\033[0m"

class SDKLogger:
    """Logger utility for SDK operations"""
    
    def __init__(self, log_level: str = None):
        """Initialize logger with configurable level"""
        self.logger = logging.getLogger('sbi_epay_sdk')
        
        # Set log level from environment or parameter
        level = log_level or os.getenv('LOG_LEVEL', 'INFO')
        self.logger.setLevel(getattr(logging, level.upper()))
        
        # Create console handler if not already exists
        if not self.logger.handlers:
            console_handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
    
    def log_operation(
        self, 
        is_logger: bool, 
        title: str, 
        status: str, 
        payload: Optional[Union[Dict[str, Any], str, Any]] = None
    ) -> None:
        """
        Log SDK operations with standardized format
        
        Args:
            is_logger (bool): Whether to enable logging for this call
            title (str): Function/operation title for reference
            status (str): Operation status ('success', 'fail', 'info', 'warning')
            payload (Optional[Union[Dict, str, Any]]): Response payload or data to log
        """
        
        if is_logger == False:
            return
        
        # Normalize status
        status = status.lower()
        
        # Prepare log message
        timestamp_string  = datetime.now().isoformat()
        dt_object = datetime.strptime(timestamp_string , "%Y-%m-%dT%H:%M:%S.%f")
        rounded_microseconds = round(dt_object.microsecond / 1000) * 1000
        dt_object = dt_object.replace(microsecond=rounded_microseconds)
        timestamp = dt_object.strftime("%Y-%m-%d %H:%M:%S") + ",{:03d}".format(dt_object.microsecond // 1000)
        log_message = f"{timestamp}"

        # Add SDK name in logger
        log_message += f" - epay_python_sdk ->"

        # Add Seperate color
        log_message = f"{CRITICAL}{log_message}{RESET}"
        
        # Format payload for logging
        formatted_payload = self._format_payload(payload)
        
        # Create structured log message
        # message = f" [{title}] Status: {status.upper()}"
        message = f" [{title} {status}]"
        
        if formatted_payload:
            message += f" | Payload: {formatted_payload}"
        
        if status in ['success', 'info']:
            response_message = f"{INFO}{message}{RESET}"
        elif status == 'warning':
            response_message = f"{WARNING}{message}{RESET}"
        elif status in ['fail', 'error', 'failure']:
            response_message = f"{ERROR}{message}{RESET}"
        else:
            response_message = f"{DEBUG}{message}{RESET}"
        
        # Log based on status level
        if status in ['success', 'info']:
            print(log_message + response_message)
        elif status == 'warning':
            print(log_message + response_message)
        elif status in ['fail', 'error', 'failure']:
            print(log_message + response_message)
        else:
            print(log_message + response_message)
    
    def _format_payload(self, payload: Any) -> str:
        """Format payload for logging"""
        if payload is None:
            return ""
        
        try:
            if isinstance(payload, dict):
                # Pretty print JSON with sensitive data masking
                masked_payload = self._mask_sensitive_data(payload)
                return json.dumps(masked_payload, indent=2, ensure_ascii=False)
            elif isinstance(payload, str):
                return payload
            else:
                return str(payload)
        except Exception as e:
            return f"<Error formatting payload.>"
    
    def _mask_sensitive_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Mask sensitive information in payloads"""
        if not isinstance(data, dict):
            return data
        
        sensitive_keys = [
            'password', 'token', 'api_key', 'secret', 'authorization',
            'credit_card', 'card_number', 'cvv', 'pin', 'otp'
        ]
        
        masked_data = {}
        for key, value in data.items():
            if any(sensitive_key in key.lower() for sensitive_key in sensitive_keys):
                if isinstance(value, str) and len(value) > 4:
                    masked_data[key] = f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"
                else:
                    masked_data[key] = "***MASKED***"
            elif isinstance(value, dict):
                masked_data[key] = self._mask_sensitive_data(value)
            elif isinstance(value, list):
                masked_data[key] = [
                    self._mask_sensitive_data(item) if isinstance(item, dict) else item 
                    for item in value
                ]
            else:
                masked_data[key] = value
        
        return masked_data

# Create a global logger instance
_sdk_logger = SDKLogger()

def log_sdk_operation(
    is_logger: bool, 
    title: str, 
    status: str, 
    payload: Optional[Union[Dict[str, Any], str, Any]] = None
) -> None:
    """
    Convenience function for logging SDK operations
    
    Args:
        is_logger (bool): Whether to enable logging for this call
        title (str): Function/operation title for reference  
        status (str): Operation status ('success', 'fail', 'info', 'warning')
        payload (Optional[Union[Dict, str, Any]]): Response payload or data to log
        
    Example:
        log_sdk_operation(True, "Payment Processing", "success", {"amount": 100, "status": "completed"})
        log_sdk_operation(True, "API Call", "fail", {"error": "Invalid credentials"})
        log_sdk_operation(False, "Silent Operation", "success", {})  # Won't log anything
    """
    _sdk_logger.log_operation(is_logger, title, status, payload)


# Additional utility functions
def configure_logger(log_level: str = "INFO", log_file: Optional[str] = None) -> None:
    """
    Configure the SDK logger with custom settings
    
    Args:
        log_level (str): Log level (DEBUG, INFO, WARNING, ERROR)
        log_file (Optional[str]): File path for logging to file
    """
    global _sdk_logger
    _sdk_logger = SDKLogger(log_level)
    
    if log_file:
        file_handler = logging.FileHandler(log_file)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        _sdk_logger.logger.addHandler(file_handler)


def log_api_request(is_logger: bool, endpoint: str, method: str, payload: Any = None) -> None:
    """Log API requests"""
    if is_logger:
        log_sdk_operation(is_logger, f"API Request - {method} {endpoint}", "info", payload)


def log_api_response(is_logger: bool, endpoint: str, status_code: int, payload: Any = None) -> None:
    """Log API responses"""
    if is_logger:
        status = "success" if 200 <= status_code < 300 else "fail"
        log_sdk_operation(is_logger, f"API Response - {endpoint} ({status_code})", status, payload)

if __name__ == "__main__":
    # Example usage
    
    # Basic logging
    log_sdk_operation(True, "Payment Processing", "success", {
        "transaction_id": "TXN123456",
        "amount": 1000.50,
        "currency": "INR",
        "status": "completed"
    })
    
    # Error logging
    log_sdk_operation(True, "Authentication", "fail", {
        "error": "Invalid API key",
        "error_code": "AUTH_001"
    })
    
    # Sensitive data masking
    log_sdk_operation(True, "Order Creation", "success", {
        "user_id": "USER123",
        "order_id": "ORDER123",
        "arnno": "ARNNO123",
    })
    
    # Disabled logging
    log_sdk_operation(False, "Silent Operation", "success", {
        "data": "This won't be logged"
    })
    
    # Configure logger for file output
    configure_logger("DEBUG", "sdk.log")
    
    # API request/response logging
    log_api_request(True, "/api/payments", "POST", {"amount": 100})
    log_api_response(True, "/api/payments", 201, {"payment_id": "PAY123"})