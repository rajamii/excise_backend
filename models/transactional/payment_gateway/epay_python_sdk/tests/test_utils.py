"""
Test cases for utility modules.
"""

import pytest
import base64
from src.utils.aes import encrypt, decrypt
from src.utils.encryption import encrypt_payload
from src.utils.decryption import decrypt_payload


class TestAESUtils:
    """Test cases for AES encryption/decryption utilities."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Create a test key (32 bytes for AES-256)
        test_key_bytes = b'test_key_1234567890123456789012'
        self.test_key = base64.b64encode(test_key_bytes).decode('utf-8')
        self.test_data = "Hello, World! This is a test message."
    
    def test_encrypt_decrypt_roundtrip(self):
        """Test that encryption and decryption work together."""
        # Encrypt the data
        encrypted = encrypt(self.test_key, self.test_data)
        
        # Verify encrypted data is different from original
        assert encrypted != self.test_data
        assert isinstance(encrypted, str)
        
        # Decrypt the data
        decrypted = decrypt(self.test_key, encrypted)
        
        # Verify decrypted data matches original
        assert decrypted == self.test_data
    
    def test_encrypt_different_outputs(self):
        """Test that encrypting the same data multiple times gives different outputs."""
        encrypted1 = encrypt(self.test_key, self.test_data)
        encrypted2 = encrypt(self.test_key, self.test_data)
        
        # Due to random IV, encrypted outputs should be different
        assert encrypted1 != encrypted2
        
        # But both should decrypt to the same original data
        assert decrypt(self.test_key, encrypted1) == self.test_data
        assert decrypt(self.test_key, encrypted2) == self.test_data
    
    def test_decrypt_invalid_data(self):
        """Test decryption with invalid data raises exception."""
        with pytest.raises(Exception):
            decrypt(self.test_key, "invalid_base64_data")
    
    def test_decrypt_wrong_key(self):
        """Test decryption with wrong key raises exception."""
        encrypted = encrypt(self.test_key, self.test_data)
        
        # Create a different key
        wrong_key_bytes = b'wrong_key_1234567890123456789012'
        wrong_key = base64.b64encode(wrong_key_bytes).decode('utf-8')
        
        with pytest.raises(Exception):
            decrypt(wrong_key, encrypted)


class TestEncryptionUtils:
    """Test cases for encryption utilities."""
    
    def setup_method(self):
        """Set up test fixtures."""
        test_key_bytes = b'test_key_1234567890123456789012'
        self.test_key = base64.b64encode(test_key_bytes).decode('utf-8')
        self.test_payload = {"customer_name": "John Doe", "amount": 1000}
    
    def test_encrypt_payload(self):
        """Test payload encryption."""
        result = encrypt_payload(self.test_key, self.test_payload)
        
        assert isinstance(result, dict)
        assert "encryptedRequest" in result
        assert isinstance(result["encryptedRequest"], str)
        assert result["encryptedRequest"] != ""


class TestDecryptionUtils:
    """Test cases for decryption utilities."""
    
    def setup_method(self):
        """Set up test fixtures."""
        test_key_bytes = b'test_key_1234567890123456789012'
        self.test_key = base64.b64encode(test_key_bytes).decode('utf-8')
    
    def test_decrypt_payload_success_status(self):
        """Test payload decryption with success status."""
        # Mock response with success status
        original_data = {"customer_id": "12345", "name": "John Doe"}
        encrypted_data = encrypt(self.test_key, '{"customer_id": "12345", "name": "John Doe"}')
        
        mock_payload = {
            "data": {
                "status": 1,
                "data": [{
                    "encryptedResponse": encrypted_data
                }]
            }
        }
        
        result = decrypt_payload(self.test_key, mock_payload)
        
        assert result["status"] == 1
        assert len(result["data"]) == 1
        assert result["data"][0]["customer_id"] == "12345"
        assert result["data"][0]["name"] == "John Doe"
    
    def test_decrypt_payload_error_status(self):
        """Test payload decryption with error status."""
        mock_payload = {
            "data": {
                "status": 0,
                "errors": ["Some error occurred"]
            }
        }
        
        result = decrypt_payload(self.test_key, mock_payload)
        
        assert result["status"] == 0
        assert "errors" in result
    
    def test_decrypt_payload_no_encrypted_response(self):
        """Test payload decryption when no encryptedResponse field."""
        mock_payload = {
            "data": {
                "status": 1,
                "data": [{
                    "customer_id": "12345",
                    "name": "John Doe"
                }]
            }
        }
        
        result = decrypt_payload(self.test_key, mock_payload)
        
        assert result["status"] == 1
        assert len(result["data"]) == 1
        assert result["data"][0]["customer_id"] == "12345"