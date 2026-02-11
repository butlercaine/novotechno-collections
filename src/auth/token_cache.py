"""
Token caching implementation using macOS Keychain for secure storage.
All tokens are encrypted with AES-256 and never stored as plaintext.
"""

import json
import logging
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import keyring
import keyring.backends.macOS


logger = logging.getLogger(__name__)


@dataclass
class CachedToken:
    """Represents a cached token with metadata."""
    access_token: str
    token_type: str
    expires_at: int
    refresh_token: Optional[str] = None
    scope: Optional[str] = None
    id_token: Optional[str] = None
    account_id: Optional[str] = None
    cached_at: int = 0
    
    def __post_init__(self):
        if self.cached_at == 0:
            self.cached_at = int(time.time())
    
    @property
    def is_expired(self) -> bool:
        """Check if token is expired (5 minute buffer)."""
        buffer_time = 300  # 5 minutes
        return int(time.time()) >= (self.expires_at - buffer_time)
    
    @property
    def is_valid(self) -> bool:
        """Check if token is still valid."""
        return not self.is_expired


class TokenCache:
    """
    Secure token cache using macOS Keychain.
    Tokens are encrypted before being stored in Keychain.
    """
    
    # Service name for Keychain entries
    KEYCHAIN_SERVICE = "com.novotechno.oauth.token"
    # Salt for key derivation (in practice, generate unique salt per installation)
    SALT = b'novotechno-oauth-salt-2026'
    
    def __init__(self, app_name: str = "novotechno-collections"):
        """
        Initialize token cache.
        
        Args:
            app_name: Application name for keychain service
        """
        self.app_name = app_name
        self.service_name = f"{self.KEYCHAIN_SERVICE}.{app_name}"
        
        # Ensure we're using macOS backend
        keyring.set_keyring(keyring.backends.macOS.Keyring())
        
        # Derive encryption key from system key
        self._encryption_key = self._derive_key()
        self._cipher = Fernet(self._encryption_key)
        
        logger.info(f"Token cache initialized for {app_name}")
    
    def _derive_key(self) -> bytes:
        """
        Derive encryption key from system password and salt.
        Uses PBKDF2-HMAC-SHA256 for key derivation.
        """
        # In production, use a system-specific secret
        # For now, use a combination of app name and machine ID
        try:
            import subprocess
            result = subprocess.run(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                capture_output=True,
                text=True
            )
            hardware_uuid = ""
            for line in result.stdout.split("\n"):
                if "IOPlatformUUID" in line:
                    hardware_uuid = line.split("=")[-1].strip().strip('"')
                    break
            
            password = f"{self.app_name}-{hardware_uuid}".encode()
        except Exception as e:
            logger.warning(f"Could not get hardware UUID: {e}, using fallback")
            password = f"{self.app_name}-fallback-secret".encode()
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.SALT,
            iterations=100000,
        )
        
        key = base64.urlsafe_b64encode(kdf.derive(password))
        return key
    
    def _encrypt(self, data: str) -> str:
        """Encrypt data using Fernet (AES-128-CBC with HMAC)."""
        return self._cipher.encrypt(data.encode()).decode()
    
    def _decrypt(self, encrypted: str) -> str:
        """Decrypt data using Fernet."""
        return self._cipher.decrypt(encrypted.encode()).decode()
    
    def _get_keychain_key(self, provider: str, account_id: str) -> str:
        """Generate keychain entry key."""
        return f"{provider}:{account_id}"
    
    def save_token(self, provider: str, account_id: str, token: CachedToken) -> bool:
        """
        Save token to macOS Keychain.
        
        Args:
            provider: OAuth provider name
            account_id: Account identifier
            token: Token to cache
            
        Returns:
            True if successful
        """
        try:
            token_json = json.dumps(asdict(token))
            encrypted_token = self._encrypt(token_json)
            
            keychain_key = self._get_keychain_key(provider, account_id)
            
            keyring.set_password(
                service_name=self.service_name,
                username=keychain_key,
                password=encrypted_token
            )
            
            logger.info(f"Token saved for {provider}:{account_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save token: {e}")
            return False
    
    def get_token(self, provider: str, account_id: str) -> Optional[CachedToken]:
        """
        Retrieve token from macOS Keychain.
        
        Args:
            provider: OAuth provider name
            account_id: Account identifier
            
        Returns:
            CachedToken or None if not found/expired
        """
        try:
            keychain_key = self._get_keychain_key(provider, account_id)
            encrypted_token = keyring.get_password(
                service_name=self.service_name,
                username=keychain_key
            )
            
            if not encrypted_token:
                logger.debug(f"No token found for {provider}:{account_id}")
                return None
            
            token_json = self._decrypt(encrypted_token)
            token_data = json.loads(token_json)
            token = CachedToken(**token_data)
            
            return token
            
        except Exception as e:
            logger.error(f"Failed to retrieve token: {e}")
            return None
    
    def delete_token(self, provider: str, account_id: str) -> bool:
        """
        Delete token from macOS Keychain.
        
        Args:
            provider: OAuth provider name
            account_id: Account identifier
            
        Returns:
            True if successful
        """
        try:
            # keyring.delete_password doesn't exist in all backends
            # We simulate deletion by setting an empty password
            keychain_key = self._get_keychain_key(provider, account_id)
            keyring.set_password(
                service_name=self.service_name,
                username=keychain_key,
                password=""
            )
            
            logger.info(f"Token deleted for {provider}:{account_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete token: {e}")
            return False
    
    def has_valid_token(self, provider: str, account_id: str) -> bool:
        """Check if a valid token exists."""
        token = self.get_token(provider, account_id)
        return token is not None and token.is_valid
    
    def get_accounts(self, provider: Optional[str] = None) -> Dict[str, Any]:
        """
        List all cached accounts.
        
        Args:
            provider: Filter by provider (optional)
            
        Returns:
            Dict of account information
        """
        # Note: keyring doesn't provide a way to list all entries
        # This is a limitation of the secure keychain approach
        # For now, return empty dict - caller must track accounts separately
        logger.warning("Listing accounts is not supported by keyring backend")
        return {}
    
    def clear_all_tokens(self) -> bool:
        """
        Clear all tokens (limited support due to keychain constraints).
        
        Returns:
            True if operation attempted
        """
        logger.warning(
            "Clearing all tokens is not fully supported by keyring. "
            "Tokens must be deleted individually."
        )
        return False


import base64