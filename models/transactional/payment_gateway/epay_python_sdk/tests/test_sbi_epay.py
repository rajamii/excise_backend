"""
Test cases for the SBI ePay SDK.
"""

import pytest
import responses
import json
from unittest.mock import patch, MagicMock

from src.SBIEPayClient import SBIEPayClient
from src.types import (
    SDKConfig, 
    CustomerEntity, 
    OrderEntity, 
    OrderSearchEntity,
    RefundEntity, 
    RefundSearchEntity
)


class TestSBIEPAY:
    """Test cases for SBIEPayClient main class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = SDKConfig(
            api_key="test_api_key",
            api_secret="test_api_secret", 
            encryption_key="dGVzdF9lbmNyeXB0aW9uX2tleQ==",  # base64 encoded test key
            base_url="https://test.epay.sbi"
        )
    
    def test_init_success(self):
        """Test successful SDK initialization."""
        sdk = SBIEPayClient(self.config)
        assert sdk.customer is not None
        assert sdk.order is not None
        assert sdk.refund is not None
    
    def test_init_missing_api_key(self):
        """Test SDK initialization with missing API key."""
        config = SDKConfig(
            api_key="",
            api_secret="test_secret",
            encryption_key="test_key"
        )
        with pytest.raises(Exception, match="API Key and Secret are required"):
            SBIEPayClient(config)
    
    def test_init_missing_encryption_key(self):
        """Test SDK initialization with missing encryption key."""
        config = SDKConfig(
            api_key="test_key",
            api_secret="test_secret", 
            encryption_key=""
        )
        with pytest.raises(Exception, match="Encryption Key is required"):
            SBIEPayClient(config)


class TestCustomer:
    """Test cases for Customer module."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = SDKConfig(
            api_key="test_api_key",
            api_secret="test_api_secret",
            encryption_key="dGVzdF9lbmNyeXB0aW9uX2tleQ==",
            base_url="https://test.epay.sbi"
        )
        self.sdk = SBIEPayClient(self.config)
    
    @responses.activate
    @patch('sbi_epay.utils.encryption.encrypt_payload')
    @patch('sbi_epay.utils.decryption.decrypt_payload')
    def test_customer_create_success(self, mock_decrypt, mock_encrypt):
        """Test successful customer creation."""
        # Mock encryption
        mock_encrypt.return_value = {"encryptedRequest": "encrypted_data"}
        
        # Mock decryption
        mock_decrypt.return_value = {
            "status": 1,
            "data": [{"customerId": "12345", "customerName": "John Doe"}]
        }
        
        # Mock token response
        responses.add(
            responses.POST,
            "https://test.epay.sbi/api/transaction/v1/token/access",
            json={"status": 1, "data": ["test_token"]},
            status=200
        )
        
        # Mock customer create response
        responses.add(
            responses.POST,
            "https://test.epay.sbi/api/transaction/v1/customer/create",
            json={"status": 1, "data": [{"customerId": "12345"}]},
            status=200
        )
        
        customer_data = CustomerEntity(
            customer_name="John Doe",
            email="john@example.com",
            phone_number="1234567890",
            address1="123 Main St",
            country="India",
            pin_code="123456"
        )
        
        result = self.sdk.customer.create(customer_data)
        
        assert result.status == 1
        assert len(result.data) > 0
    
    @responses.activate
    @patch('sbi_epay.utils.decryption.decrypt_payload')
    def test_customer_fetch_success(self, mock_decrypt):
        """Test successful customer fetch."""
        # Mock decryption
        mock_decrypt.return_value = {
            "status": 1,
            "data": [{"customerId": "12345", "customerName": "John Doe"}]
        }
        
        # Mock token response
        responses.add(
            responses.POST,
            "https://test.epay.sbi/api/transaction/v1/token/access",
            json={"status": 1, "data": ["test_token"]},
            status=200
        )
        
        # Mock customer fetch response
        responses.add(
            responses.GET,
            "https://test.epay.sbi/api/transaction/v1/customer/12345",
            json={"status": 1, "data": [{"customerId": "12345"}]},
            status=200
        )
        
        result = self.sdk.customer.fetch("12345")
        
        assert result.status == 1
        assert len(result.data) > 0
    
    def test_customer_fetch_missing_id(self):
        """Test customer fetch with missing customer ID."""
        with pytest.raises(Exception, match="customer ID is required"):
            self.sdk.customer.fetch("")
    
    @responses.activate
    @patch('sbi_epay.utils.decryption.decrypt_payload')
    def test_customer_update_status_success(self, mock_decrypt):
        """Test successful customer status update."""
        # Mock decryption
        mock_decrypt.return_value = {
            "status": 1,
            "data": [{"customerId": "12345", "status": "ACTIVE"}]
        }
        
        # Mock token response
        responses.add(
            responses.POST,
            "https://test.epay.sbi/api/transaction/v1/token/access",
            json={"status": 1, "data": ["test_token"]},
            status=200
        )
        
        # Mock customer status update response
        responses.add(
            responses.POST,
            "https://test.epay.sbi/api/transaction/v1/customer/12345/ACTIVE",
            json={"status": 1, "data": [{"status": "updated"}]},
            status=200
        )
        
        result = self.sdk.customer.update_status("12345", "ACTIVE")
        
        assert result.status == 1
        assert len(result.data) > 0


class TestOrder:
    """Test cases for Order module."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = SDKConfig(
            api_key="test_api_key",
            api_secret="test_api_secret",
            encryption_key="dGVzdF9lbmNyeXB0aW9uX2tleQ==",
            base_url="https://test.epay.sbi"
        )
        self.sdk = SBIEPayClient(self.config)
    
    @responses.activate
    @patch('sbi_epay.utils.encryption.encrypt_payload')
    @patch('sbi_epay.utils.decryption.decrypt_payload')
    def test_order_create_success(self, mock_decrypt, mock_encrypt):
        """Test successful order creation."""
        # Mock encryption
        mock_encrypt.return_value = {"encryptedRequest": "encrypted_data"}
        
        # Mock decryption
        mock_decrypt.return_value = {
            "status": 1,
            "data": [{"orderId": "67890", "orderRefNumber": "ORD123"}]
        }
        
        # Mock token response
        responses.add(
            responses.POST,
            "https://test.epay.sbi/api/transaction/v1/token/access",
            json={"status": 1, "data": ["test_token"]},
            status=200
        )
        
        # Mock order create response
        responses.add(
            responses.POST,
            "https://test.epay.sbi/api/transaction/v1/order/create",
            json={"status": 1, "data": [{"orderId": "67890"}]},
            status=200
        )
        
        order_data = OrderEntity(
            currency_code="INR",
            order_amount=1000.0,
            order_ref_number="ORD123",
            return_url="https://example.com/return"
        )
        
        result = self.sdk.order.create(order_data)
        
        assert result.status == 1
        assert len(result.data) > 0
    
    @responses.activate
    @patch('sbi_epay.utils.encryption.encrypt_payload')
    @patch('sbi_epay.utils.decryption.decrypt_payload')
    def test_order_search_success(self, mock_decrypt, mock_encrypt):
        """Test successful order search."""
        # Mock encryption
        mock_encrypt.return_value = {"encryptedRequest": "encrypted_data"}
        
        # Mock decryption
        mock_decrypt.return_value = {
            "status": 1,
            "data": [{"orderId": "67890", "status": "SUCCESS"}]
        }
        
        # Mock token response
        responses.add(
            responses.POST,
            "https://test.epay.sbi/api/transaction/v1/token/access",
            json={"status": 1, "data": ["test_token"]},
            status=200
        )
        
        # Mock order search response
        responses.add(
            responses.POST,
            "https://test.epay.sbi/api/transaction/v1/order/status",
            json={"status": 1, "data": [{"orderId": "67890"}]},
            status=200
        )
        
        search_data = OrderSearchEntity(
            order_amount=1000.0,
            order_ref_number="ORD123"
        )
        
        result = self.sdk.order.search(search_data)
        
        assert result.status == 1
        assert len(result.data) > 0


class TestRefund:
    """Test cases for Refund module."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = SDKConfig(
            api_key="test_api_key",
            api_secret="test_api_secret",
            encryption_key="dGVzdF9lbmNyeXB0aW9uX2tleQ==",
            base_url="https://test.epay.sbi"
        )
        self.sdk = SBIEPayClient(self.config)
    
    @responses.activate
    @patch('sbi_epay.utils.encryption.encrypt_payload')
    @patch('sbi_epay.utils.decryption.decrypt_payload')
    def test_refund_book_success(self, mock_decrypt, mock_encrypt):
        """Test successful refund booking."""
        # Mock encryption
        mock_encrypt.return_value = {"encryptedRequest": "encrypted_data"}
        
        # Mock decryption
        mock_decrypt.return_value = {
            "status": 1,
            "data": [{"refundId": "REF123", "status": "INITIATED"}]
        }
        
        # Mock token response
        responses.add(
            responses.POST,
            "https://test.epay.sbi/api/transaction/v1/token/access",
            json={"status": 1, "data": ["test_token"]},
            status=200
        )
        
        # Mock refund book response
        responses.add(
            responses.POST,
            "https://test.epay.sbi/api/transaction/v1/refund/book",
            json={"status": 1, "data": [{"refundId": "REF123"}]},
            status=200
        )
        
        refund_data = RefundEntity(
            refund_type="FULL",
            refund_amount=500.0,
            atrn_number="ATRN12345"
        )
        
        result = self.sdk.refund.book(refund_data)
        
        assert result.status == 1
        assert len(result.data) > 0
    
    @responses.activate
    @patch('sbi_epay.utils.encryption.encrypt_payload')
    @patch('sbi_epay.utils.decryption.decrypt_payload')
    def test_refund_search_success(self, mock_decrypt, mock_encrypt):
        """Test successful refund search."""
        # Mock encryption
        mock_encrypt.return_value = {"encryptedRequest": "encrypted_data"}
        
        # Mock decryption
        mock_decrypt.return_value = {
            "status": 1,
            "data": [{"refundId": "REF123", "status": "SUCCESS"}]
        }
        
        # Mock token response
        responses.add(
            responses.POST,
            "https://test.epay.sbi/api/transaction/v1/token/access",
            json={"status": 1, "data": ["test_token"]},
            status=200
        )
        
        # Mock refund search response
        responses.add(
            responses.POST,
            "https://test.epay.sbi/api/transaction/v1/refund/search",
            json={"status": 1, "data": [{"refundId": "REF123"}]},
            status=200
        )
        
        search_data = RefundSearchEntity(
            atrn_number="ATRN12345",
            arrn_number="ARRN12345",
            sbi_order_ref_number="SBI123",
            refund_status="SUCCESS",
            refund_type="FULL",
            from_date=1640995200,  # 2022-01-01
            to_date=1672531199     # 2022-12-31
        )
        
        result = self.sdk.refund.search(search_data)
        
        assert result.status == 1
        assert len(result.data) > 0


class TestErrorHandling:
    """Test cases for error handling."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = SDKConfig(
            api_key="test_api_key",
            api_secret="test_api_secret",
            encryption_key="dGVzdF9lbmNyeXB0aW9uX2tleQ==",
            base_url="https://test.epay.sbi"
        )
        self.sdk = SBIEPayClient(self.config)
    
    @responses.activate
    def test_api_error_response(self):
        """Test handling of API error responses."""
        # Mock token response
        responses.add(
            responses.POST,
            "https://test.epay.sbi/api/transaction/v1/token/access",
            json={"status": 1, "data": ["test_token"]},
            status=200
        )
        
        # Mock error response
        responses.add(
            responses.GET,
            "https://test.epay.sbi/api/transaction/v1/customer/invalid",
            json={
                "status": 0,
                "errors": [{"errorMessage": "Customer not found"}]
            },
            status=400
        )
        
        with pytest.raises(Exception, match="Customer not found"):
            self.sdk.customer.fetch("invalid")
    
    @responses.activate
    def test_network_error(self):
        """Test handling of network errors."""
        # Mock token response
        responses.add(
            responses.POST,
            "https://test.epay.sbi/api/transaction/v1/token/access",
            json={"status": 1, "data": ["test_token"]},
            status=200
        )
        
        # Mock network error
        responses.add(
            responses.GET,
            "https://test.epay.sbi/api/transaction/v1/customer/12345",
            body=ConnectionError("Network error")
        )
        
        with pytest.raises(Exception, match="Request failed"):
            self.sdk.customer.fetch("12345")