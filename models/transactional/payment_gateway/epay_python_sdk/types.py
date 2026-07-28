"""
Type definitions for the SBI ePay SDK.
"""

from typing import Dict, List, Optional, Union, Any, TypeAlias
from dataclasses import dataclass, asdict
import json


# Generic types
KeyValueObject = Dict[str, Union[str, int, bool]]


@dataclass
class SDKCredentials:
    """Credentials options for the SDK client."""
    api_key: str
    api_secret: str
    encryption_key: str

"""Environment options for the SDK client."""
Environment: TypeAlias = str

"""Logging options for the SDK client."""   
Logging = bool

"""Response Type options for the SDK client."""   
ResponseType = str

@dataclass
class RequestEntity:
    """Request types."""
    encrypted_request: str


@dataclass
class EncryptedResponseEntity:
    """Response types."""
    encrypted_response: str

@dataclass
class ErrorEntity:
    """Error entity for API responses."""
    errorMessage: str
    errorCode: Optional[str] = None

@dataclass
class ResponseEntity:
    """Generic response entity."""
    status: int
    data: Optional[List[Any]] = None
    errors: Optional[List[Any]] = None

    @classmethod
    def error(cls, error_message: str, error_code: str = None) -> 'ResponseEntity':
        """Create an error response entity."""
        return cls(
            status=0,
            errors=[ErrorEntity(errorCode=error_code, errorMessage=error_message)]
        )

    @classmethod
    def success(cls, data: List[Any] = None) -> 'ResponseEntity':
        """Create a success response entity."""
        return cls(
            status=1,
            data=data or []
        )

    def to_dict(self):
        return {k: v for k, v in asdict(self).items() if v is not None}

    def to_json(self):
        return json.dumps(self.to_dict())


@dataclass
class CustomerEntity:
    """Customer entity for API requests."""
    customerName: str
    email: str
    phoneNumber: str
    address1: str
    country: str
    pinCode: str
    address2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    gstIn: Optional[str] = None
    gstInAddress: Optional[str] = None


@dataclass
class OrderEntity:
    """Order entity for API requests."""
    currencyCode: str
    orderAmount: float
    orderRefNumber: str
    returnUrl: str
    customerId: Optional[str] = None
    sbiOrderRefNumber: Optional[str] = None
    status: Optional[str] = None
    otherDetails: Optional[str] = None
    expiry: Optional[int] = None
    multiAccounts: Optional[str] = None
    paymentMode: Optional[str] = None
    orderHash: Optional[str] = None
    transactionUrl: Optional[str] = None
    orderRetryCount: Optional[int] = None
    thirdPartyDetails: Optional[str] = None


@dataclass
class OrderSearchEntity:
    """Order search entity for API requests."""
    orderAmount: float
    orderRefNumber: str
    sbiOrderRefNumber: Optional[str] = None
    atrnNumber: Optional[str] = None


@dataclass
class RefundEntity:
    """Refund entity for API requests."""
    refundType: str
    refundAmount: float
    atrnNumber: str
    remark: Optional[str] = None


@dataclass
class RefundSearchEntity:
    """Refund search entity for API requests."""
    atrnNumber: str
    arrnNumber: str
    sbiOrderRefNumber: str
    refundStatus: str
    refundType: str
    fromDate: int
    toDate: int