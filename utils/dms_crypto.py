import base64
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
from django.conf import settings

try:
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

logger = logging.getLogger(__name__)


class CryptoConfigurationError(RuntimeError):
    pass


class JavaCompatibleCrypto:
    """
    Implements the AES-CBC + HMAC-SHA256 protocol used by the Sikkim Document Management System (DMS / FileServerApp).
    
    Encryption: AES/CBC/PKCS5Padding (PKCS7 in cryptography library), 16-byte zero IV.
    Signature: HMAC-SHA256 computed on the Base64 ciphertext using the decoded secret key.
    """

    def __init__(self, key_path=None, raw_key=None):
        if not HAS_CRYPTO:
            raise CryptoConfigurationError("The 'cryptography' library is not installed.")

        key_str = raw_key or getattr(settings, "DMS_AES_KEY", os.getenv("DMS_AES_KEY", "")).strip()

        # If direct key string not given, check key file path
        if not key_str:
            configured_path = key_path or getattr(settings, "DMS_AES_KEY_PATH", os.getenv("DMS_AES_KEY_PATH", ""))
            if configured_path:
                p = Path(configured_path)
                if not p.is_absolute():
                    p = Path(settings.BASE_DIR) / p
                if p.is_file():
                    key_str = p.read_text(encoding="utf-8").strip()

        if not key_str:
            # Fallback to the government allocated key for DMS20260006
            key_str = "SmpYMm44VVM0VHVld0t3OTl3Q1JlRHQxbXMzeTFWank="

        try:
            self.key = base64.b64decode(key_str, validate=True)
        except Exception as exc:
            raise CryptoConfigurationError("AES key must contain valid Base64 encoded text.") from exc

        if len(self.key) not in (16, 24, 32):
            raise CryptoConfigurationError(f"Decoded AES key must be 16, 24, or 32 bytes (got {len(self.key)} bytes).")

    def encrypt_text(self, plaintext: str) -> str:
        """Encrypts plaintext using AES-CBC with zero IV and PKCS7 padding, returned as Base64."""
        padder = padding.PKCS7(algorithms.AES.block_size).padder()
        padded = padder.update(plaintext.encode("utf-8")) + padder.finalize()
        cipher = Cipher(algorithms.AES(self.key), modes.CBC(b"\x00" * 16))
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(padded) + encryptor.finalize()
        return base64.b64encode(ciphertext).decode("ascii")

    def decrypt_text(self, encrypted: str) -> str:
        """Decrypts Base64 encrypted text using AES-CBC with zero IV and PKCS7 unpadding."""
        ciphertext = base64.b64decode(encrypted, validate=True)
        cipher = Cipher(algorithms.AES(self.key), modes.CBC(b"\x00" * 16))
        decryptor = cipher.decryptor()
        padded = decryptor.update(ciphertext) + decryptor.finalize()
        unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
        return (unpadder.update(padded) + unpadder.finalize()).decode("utf-8")

    def hmac_b64(self, value: str) -> str:
        """Generates HMAC-SHA256 signature in Base64 for the given value (usually the encrypted ciphertext)."""
        return base64.b64encode(hmac.new(self.key, value.encode("utf-8"), hashlib.sha256).digest()).decode("ascii")

    def make_upload_payload(
        self,
        *,
        arn: str,
        document_id: str | int,
        doc_type_name: str,
        doc_number: str | int,
        file_bytes: bytes,
        beneficiary_mobile: str
    ) -> tuple[str, str]:
        """
        Creates the signed, encrypted payload required by FileServerApp (onChangeFileSubmit / upload).
        Returns:
            (encrypted_data, transaction_signature)
        """
        payload = {
            "arn": str(arn),
            "documentId": str(document_id),
            "docTypeName": str(doc_type_name),
            "docNumber": str(doc_number),
            "file": base64.b64encode(file_bytes).decode("ascii"),
            "beneficiaryMobile": str(beneficiary_mobile or ""),
        }
        # Compact JSON matching JSONObject.toString() expected by FileServerApp
        plaintext = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        encrypted_data = self.encrypt_text(plaintext)
        signature = self.hmac_b64(encrypted_data)
        return encrypted_data, signature
