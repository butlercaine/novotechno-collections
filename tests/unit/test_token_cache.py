"""
Unit tests for token cache module.
Tests secure token storage in macOS Keychain.
"""

import unittest
import time
import json
from unittest.mock import patch, MagicMock, call
from cryptography.fernet import Fernet
from src.auth.token_cache import TokenCache, CachedToken


class TestCachedToken(unittest.TestCase):
    """Test CachedToken dataclass functionality."""
    
    def test_cached_token_creation(self):
        """Test token creation and default values."""
        now = int(time.time())
        token = CachedToken(
            access_token="test_token",
            token_type="Bearer",
            expires_at=now + 3600
        )
        
        self.assertEqual(token.access_token, "test_token")
        self.assertEqual(token.token_type, "Bearer")
        self.assertEqual(token.expires_at, now + 3600)
        self.assertIsNone(token.refresh_token)
        self.assertIsNone(token.scope)
        self.assertIsNone(token.id_token)
        self.assertIsNone(token.account_id)
        self.assertAlmostEqual(token.cached_at, now, delta=1)
    
    def test_token_expiration_check(self):
        """Test token expiration logic with 5-minute buffer."""
        now = int(time.time())
        
        # Token valid for more than 5 minutes
        token_valid = CachedToken(
            access_token="valid",
            token_type="Bearer",
            expires_at=now + 3600
        )
        self.assertFalse(token_valid.is_expired)
        self.assertTrue(token_valid.is_valid)
        
        # Token expires in less than 5 minutes
        token_near_expiry = CachedToken(
            access_token="near_expiry",
            token_type="Bearer",
            expires_at=now + 240  # 4 minutes
        )
        self.assertTrue(token_near_expiry.is_expired)
        self.assertFalse(token_near_expiry.is_valid)
        
        # Already expired token
        token_expired = CachedToken(
            access_token="expired",
            token_type="Bearer",
            expires_at=now - 100
        )
        self.assertTrue(token_expired.is_expired)
        self.assertFalse(token_expired.is_valid)
    
    def test_token_expiration_boundary(self):
        """Test the exact 5-minute boundary."""
        now = int(time.time())
        
        # Exactly 5 minutes = expired (buffer)
        token = CachedToken(
            access_token="boundary",
            token_type="Bearer",
            expires_at=now + 300
        )
        self.assertTrue(token.is_expired)


class TestTokenCache(unittest.TestCase):
    """Test TokenCache keychain operations."""
    
    def setUp(self):
        """Set up test fixtures before each test."""
        self.cache = TokenCache(app_name="test-app")
        self.provider = "test-provider"
        self.account_id = "test-user@example.com"
        
        # Sample token
        now = int(time.time())
        self.test_token = CachedToken(
            access_token="test_access_token_12345",
            token_type="Bearer",
            expires_at=now + 3600,
            refresh_token="test_refresh_token_67890",
            scope="read write",
            account_id=self.account_id,
        )
    
    @patch('keyring.set_password')
    @patch('keyring.get_password')
    def test_save_and_retrieve_token(self, mock_get, mock_set):
        """Test saving and retrieving a token from Keychain."""
        # Mock successful save
        mock_set.return_value = None
        
        # Save token
        result = self.cache.save_token(self.provider, self.account_id, self.test_token)
        self.assertTrue(result)
        
        # Verify set_password was called
        expected_key = f"{self.provider}:{self.account_id}"
        mock_set.assert_called_once()
        call_args = mock_set.call_args
        self.assertEqual(call_args[1]['service_name'], self.cache.service_name)
        self.assertEqual(call_args[1]['username'], expected_key)
        
        # The password should be encrypted (not plaintext)
        encrypted_password = call_args[1]['password']
        self.assertNotEqual(encrypted_password, json.dumps({"access_token": "test"}))
        
        # Mock retrieval
        mock_get.return_value = encrypted_password
        
        # Retrieve token
        retrieved = self.cache.get_token(self.provider, self.account_id)
        
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.access_token, self.test_token.access_token)
        self.assertEqual(retrieved.token_type, self.test_token.token_type)
        self.assertEqual(retrieved.expires_at, self.test_token.expires_at)
        self.assertEqual(retrieved.refresh_token, self.test_token.refresh_token)
        self.assertEqual(retrieved.scope, self.test_token.scope)
    
    @patch('keyring.set_password')
    def test_save_token_failure(self, mock_set):
        """Test handling save failures."""
        mock_set.side_effect = Exception("Keychain error")
        
        result = self.cache.save_token(self.provider, self.account_id, self.test_token)
        self.assertFalse(result)
    
    @patch('keyring.get_password')
    def test_get_nonexistent_token(self, mock_get):
        """Test retrieving non-existent token."""
        mock_get.return_value = None
        
        result = self.cache.get_token(self.provider, self.account_id)
        self.assertIsNone(result)
    
    @patch('keyring.get_password')
    def test_get_token_decryption_failure(self, mock_get):
        """Test handling corrupted/invalid encrypted data."""
        mock_get.return_value = "invalid-encrypted-data"
        
        result = self.cache.get_token(self.provider, self.account_id)
        self.assertIsNone(result)
    
    @patch('keyring.set_password')
    def test_delete_token(self, mock_set):
        """Test token deletion."""
        mock_set.return_value = None
        
        result = self.cache.delete_token(self.provider, self.account_id)
        self.assertTrue(result)
        
        # Verify we set empty password (simulating deletion)
        expected_key = f"{self.provider}:{self.account_id}"
        mock_set.assert_called_once()
        call_args = mock_set.call_args
        self.assertEqual(call_args[1]['service_name'], self.cache.service_name)
        self.assertEqual(call_args[1]['username'], expected_key)
        self.assertEqual(call_args[1]['password'], "")
    
    @patch('keyring.get_password')
    def test_has_valid_token_true(self, mock_get):
        """Test valid token check when token exists and is valid."""
        now = int(time.time())
        valid_token = CachedToken(
            access_token="valid_token",
            token_type="Bearer",
            expires_at=now + 3600  # 1 hour from now
        )
        token_json = json.dumps({**valid_token.__dict__})
        mock_get.return_value = self.cache._encrypt(token_json)
        
        result = self.cache.has_valid_token(self.provider, self.account_id)
        self.assertTrue(result)
    
    @patch('keyring.get_password')
    def test_has_valid_token_expired(self, mock_get):
        """Test valid token check when token is expired."""
        now = int(time.time())
        expired_token = CachedToken(
            access_token="expired_token",
            token_type="Bearer",
            expires_at=now - 100  # 100 seconds ago
        )
        token_json = json.dumps({**expired_token.__dict__})
        mock_get.return_value = self.cache._encrypt(token_json)
        
        result = self.cache.has_valid_token(self.provider, self.account_id)
        self.assertFalse(result)
    
    @patch('keyring.get_password')
    def test_has_valid_token_none(self, mock_get):
        """Test valid token check when token doesn't exist."""
        mock_get.return_value = None
        
        result = self.cache.has_valid_token(self.provider, self.account_id)
        self.assertFalse(result)
    
    def test_encryption_decryption(self):
        """Test that encryption/decryption works correctly."""
        original_text = "This is a secret token value!"
        
        encrypted = self.cache._encrypt(original_text)
        self.assertNotEqual(encrypted, original_text)
        self.assertNotIn("secret", encrypted)
        
        decrypted = self.cache._decrypt(encrypted)
        self.assertEqual(decrypted, original_text)
    
    def test_encryption_different_keys(self):
        """Test that different cache instances can decrypt if they derive same key."""
        original_text = "Test secret"
        
        cache1 = TokenCache(app_name="test-app")
        cache2 = TokenCache(app_name="test-app")
        
        encrypted1 = cache1._encrypt(original_text)
        encrypted2 = cache2._encrypt(original_text)
        
        # Both should be able to decrypt their own and each other's
        self.assertEqual(cache2._decrypt(encrypted1), original_text)
        self.assertEqual(cache1._decrypt(encrypted2), original_text)
    
    @patch('subprocess.run')
    def test_key_derivation_with_hardware_uuid(self, mock_run):
        """Test key derivation uses hardware UUID when available."""
        mock_run.return_value.stdout = """
        "IOPlatformUUID" = "12345678-1234-1234-1234-123456789ABC"
        """
        mock_run.return_value.returncode = 0
        
        cache = TokenCache(app_name="test-app")
        
        # Should generate consistent key based on HW UUID
        cache2 = TokenCache(app_name="test-app")
        
        text = "test"
        self.assertEqual(cache._decrypt(cache._encrypt(text)), text)
        self.assertEqual(cache2._decrypt(cache._encrypt(text)), text)
    
    @patch('subprocess.run')
    def test_key_derivation_fallback(self, mock_run):
        """Test key derivation falls back when UUID not available."""
        mock_run.side_effect = Exception("ioreg not found")
        
        cache = TokenCache(app_name="test-app")
        
        # Should still work with fallback
        encrypted = cache._encrypt("test")
        self.assertEqual(cache._decrypt(encrypted), "test")
    
    def test_critical_condition_c001_no_plaintext(self):
        """Critical condition C-001: Token must never exist as plaintext file."""
        import tempfile
        import os
        
        with patch('keyring.set_password') as mock_set:
            mock_set.return_value = None
            
            # Save token
            self.cache.save_token(self.provider, self.account_id, self.test_token)
            
            # Verify the data written to keychain is encrypted
            call_args = mock_set.call_args
            password_written = call_args[1]['password']
            
            # Should be encrypted (base64-like string, not JSON)
            self.assertNotIn(self.test_token.access_token, password_written)
            self.assertNotIn("access_token", password_written)
            
            # Should NOT be valid JSON
            with self.assertRaises(Exception):
                json.loads(password_written)
            
            # The encrypted data should be a reasonable length
            self.assertGreater(len(password_written), 50)
    
    @patch('keyring.get_password')
    def test_critical_condition_c002_refresh_before_expiry(self, mock_get):
        """Critical condition C-002: Token refresh before expiry (5 min buffer)."""
        now = int(time.time())
        
        # Token expires in 10 minutes (should NOT be considered expired)
        token_with_time = CachedToken(
            access_token="token_with_time",
            token_type="Bearer",
            expires_at=now + 600
        )
        token_json = json.dumps({**token_with_time.__dict__})
        mock_get.return_value = self.cache._encrypt(token_json)
        
        retrieved = self.cache.get_token(self.provider, self.account_id)
        
        # Token should be valid (> 5 minutes remaining)
        self.assertFalse(retrieved.is_expired)
        self.assertTrue(retrieved.is_valid)


class TestTokenCacheIntegration(unittest.TestCase):
    """Integration tests with real keychain (skip in CI)."""
    
    @unittest.skipIf(
        'CI' in __import__('os').environ,
        "Skipping keychain integration test in CI"
    )
    def test_real_keychain_operations(self):
        """Test with real macOS Keychain (manual run only)."""
        cache = TokenCache(app_name="test-integration-app")
        
        now = int(time.time())
        test_token = CachedToken(
            access_token="real_test_token_12345",
            token_type="Bearer",
            expires_at=now + 3600,
            account_id="integration-test@example.com"
        )
        
        # Save
        result = cache.save_token("integration", "test", test_token)
        self.assertTrue(result)
        
        # Retrieve
        retrieved = cache.get_token("integration", "test")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.access_token, test_token.access_token)
        
        # Check validity
        self.assertTrue(retrieved.is_valid)
        
        # Delete
        result = cache.delete_token("integration", "test")
        self.assertTrue(result)
        
        # Verify deletion
        deleted = cache.get_token("integration", "test")
        # Note: deletion simulation sets empty password, 
        # which will fail decryption (returns None)
        self.assertIsNone(deleted)


if __name__ == '__main__':
    unittest.main()