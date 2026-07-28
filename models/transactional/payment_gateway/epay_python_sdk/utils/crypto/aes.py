"""
AES encryption/decryption utilities using AES-GCM.
"""

import base64
import os
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

# Constants for GCM parameters
GCM_IV_LENGTH = 16  # in bytes
GCM_TAG_LENGTH = 16  # in bytes (128 bits / 8)


def import_key(base64_key: str) -> bytes:
    """
    Import a Base64-encoded AES key.
    
    Args:
        base64_key: The Base64-encoded AES key
        
    Returns:
        The decoded AES key as bytes
    """
    return base64.b64decode(base64_key)


def encrypt(key: str, value: str) -> str:
    """
    Encrypt a value using AES-GCM.
    
    Args:
        key: The Base64-encoded encryption key
        value: The plaintext value to encrypt
        
    Returns:
        Base64 encoded ciphertext with IV prepended
    """
    # print(f"🔄 Aes key: {key}")
    # print(f"🔄 Aes value: {value}")

    # Import the key
    aes_key = import_key(key)
    
    # Generate random IV
    iv = os.urandom(GCM_IV_LENGTH)
    
    # Create cipher
    cipher = Cipher(algorithms.AES(aes_key), modes.GCM(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    
    # Encrypt the plaintext
    ciphertext = encryptor.update(value.encode('utf-8')) + encryptor.finalize()
    
    # Get the authentication tag
    tag = encryptor.tag
    
    # Combine IV, ciphertext, and tag
    encrypted_data = iv + ciphertext + tag
    
    # print(f"\033[38;5;208m✅🔐 Aes encrypted_data: {base64.b64encode(encrypted_data).decode('utf-8')}\033[0m")
    # print("-" * 10)
    
    # Encode to Base64 and return
    return base64.b64encode(encrypted_data).decode('utf-8')


def decrypt(key: str, encrypted_base64: str) -> str:
    """
    Decrypt a value using AES-GCM.
    
    Args:
        key: The Base64-encoded encryption key
        encrypted_base64: Base64 encoded ciphertext with IV prepended
        
    Returns:
        The decrypted plaintext value
    """
    # Import the key
    aes_key = import_key(key)
    
    # Decode Base64
    encrypted_data = base64.b64decode(encrypted_base64)
    
    # Extract IV, ciphertext, and tag
    iv = encrypted_data[:GCM_IV_LENGTH]
    tag = encrypted_data[-GCM_TAG_LENGTH:]
    ciphertext = encrypted_data[GCM_IV_LENGTH:-GCM_TAG_LENGTH]
    
    # Create cipher
    cipher = Cipher(algorithms.AES(aes_key), modes.GCM(iv, tag), backend=default_backend())
    decryptor = cipher.decryptor()
    
    # Decrypt the ciphertext
    plaintext = decryptor.update(ciphertext) + decryptor.finalize()

    # print(f"\033[38;5;208m✅🔓 Aes decrypted_data: {plaintext.decode('utf-8')}\033[0m")
    # print("-" * 10)
    
    # Decode and return
    return plaintext.decode('utf-8')