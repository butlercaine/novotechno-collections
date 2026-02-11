"""
Unit tests for token validator module.
Tests token validation, refresh monitoring, and DEGRADED mode.
"""

import unittest
import time
from unittest.mock import MagicMock, patch
from src.auth.token_validator import TokenValidator
from src.auth.token_cache import CachedToken


class MockTokenCache:
    """Mock token cache for testing."""
    
    def __init__(self, tokens=None):
        self.tokens = tokens or {}
    
    def get_token(self, provider, account_id):
        return self.tokens.get(f"{provider}:{account_id}")
    
    def save_token(self, provider, account_id, token):
        self.tokens[f"{provider}:{account_id}"] = token
        return True


class TestTokenValidator(unittest.TestCase):
    """Test TokenValidator functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_cache = MockTokenCache()
        self.validator = TokenValidator(self.mock_cache, provider="test-provider")
    
    def test_validate_token_success(self):
        """Test successful token validation."""
        now = int(time.time())
        token = CachedToken(
            access_token="valid_token_12345",
            token_type="Bearer",
            expires_at=now + 3600,  # 1 hour from now
            account_id="test-user"
        )
        self.mock_cache.tokens["test-provider:test-user"] = token
        
        result = self.validator.validate_before_request("test-user")
        
        self.assertIsNotNone(result)
        self.assertEqual(result["access_token"], "valid_token_12345")
        self.assertEqual(result["account_id"], "test-user")
        self.assertFalse(self.validator.degraded_mode)
    
    def test_validate_token_expired_buffer(self):
        """Test token refresh when within buffer period."""
        now = int(time.time())
        token = CachedToken(
            access_token="expiring_token",
            token_type="Bearer",
            expires_at=now + 100,  # Only 100 seconds remaining (<300s buffer)
            refresh_token="refresh_123",
            account_id="test-user"
        )
        self.mock_cache.tokens["test-provider:test-user"] = token
        
        # Mock the cache save to prevent actual token update in test
        self.mock_cache.save_token = MagicMock(return_value=True)
        
        with patch.object(self.validator.cache, 'save_token', return_value=True):
            result = self.validator.validate_before_request("test-user", buffer_seconds=300)
        
        self.assertIsNotNone(result)
        self.assertIn("access_token", result)
        self.assertEqual(result["account_id"], "test-user")
    
    def test_validate_no_token_raises(self):
        """Test that missing token raises exception."""
        with self.assertRaises(Exception) as context:
            self.validator.validate_before_request("nonexistent-user")
        
        self.assertIn("No tokens found", str(context.exception))
    
    def test_degraded_mode_after_max_attempts(self):
        """Test DEGRADED mode after 3 refresh failures."""
        now = int(time.time())
        token = CachedToken(
            access_token="failing_token",
            token_type="Bearer",
            expires_at=now + 50,  # About to expire
            refresh_token="refresh_123",
            account_id="test-user"
        )
        self.mock_cache.tokens["test-provider:test-user"] = token
        
        # Mock refresh to always fail
        with patch.object(self.validator.cache, 'save_token', side_effect=Exception("Refresh failed")):
            for attempt in range(3):
                with self.assertRaises(Exception):
                    self.validator.validate_before_request("test-user", buffer_seconds=300)
        
        self.assertTrue(self.validator.degraded_mode)
        self.assertEqual(self.validator.refresh_attempts, 3)
    
    def test_degraded_mode_prevents_requests(self):
        """Test that DEGRADED mode prevents further requests."""
        self.validator.degraded_mode = True
        self.validator.refresh_attempts = 3
        
        with self.assertRaises(Exception) as context:
            self.validator.validate_before_request("test-user")
        
        self.assertIn("DEGRADED_MODE", str(context.exception))
    
    def test_audit_logging(self):
        """Test refresh audit logging."""
        # Mock the audit log file
        with patch('builtins.open', create=True) as mock_open:
            mock_file = MagicMock()
            mock_open.return_value.__enter__.return_value = mock_file
            
            old_tid = "old_token_12345"
            new_tid = "new_token_67890"
            
            self.validator.log_refresh_audit(old_tid, new_tid)
            
            # Verify file was opened for append
            mock_file.write.assert_called_once()
            call_args = mock_file.write.call_args[0][0]
            self.assertIn("TOKEN_REFRESH_AUDIT", call_args)
            self.assertIn("old_token_12", call_args)
            self.assertIn("new_token_67", call_args)
    
    def test_status_check_valid_token(self):
        """Test status check with valid token."""
        now = int(time.time())
        token = CachedToken(
            access_token="status_check_token",
            token_type="Bearer",
            expires_at=now + 1800,
            cached_at=now,
            account_id="test-user"
        )
        self.mock_cache.tokens["test-provider:test-user"] = token
        
        status = self.validator.get_status("test-user")
        
        self.assertEqual(status["account_id"], "test-user")
        self.assertEqual(status["status"], "ACTIVE")
        self.assertFalse(status["degraded_mode"])
        self.assertGreater(status["token_expires_in_seconds"], 0)
        self.assertTrue(status["token_valid"])
    
    def test_status_check_no_token(self):
        """Test status check with no token."""
        status = self.validator.get_status("nonexistent-user")
        
        self.assertEqual(status["account_id"], "nonexistent-user")
        self.assertEqual(status["status"], "NO_TOKEN")
        self.assertFalse(status["degraded_mode"])
    
    def test_status_check_degraded_mode(self):
        """Test status check in degraded mode."""
        # First add a token to the cache
        now = int(time.time())
        token = CachedToken(
            access_token="degraded_token",
            token_type="Bearer",
            expires_at=now + 1800,
            cached_at=now,
            account_id="test-user"
        )
        self.mock_cache.tokens["test-provider:test-user"] = token
        
        # Now set degraded mode
        self.validator.degraded_mode = True
        self.validator.refresh_attempts = 3
        
        status = self.validator.get_status("test-user")
        
        self.assertEqual(status["status"], "DEGRADED")
        self.assertTrue(status["degraded_mode"])
        self.assertEqual(status["refresh_attempts"], 3)
    
    def test_reset_degraded_mode(self):
        """Test resetting degraded mode."""
        self.validator.degraded_mode = True
        self.validator.refresh_attempts = 3
        
        result = self.validator.reset_degraded_mode()
        
        self.assertTrue(result)
        self.assertFalse(self.validator.degraded_mode)
        self.assertEqual(self.validator.refresh_attempts, 0)
    
    def test_reset_degraded_mode_when_not_degraded(self):
        """Test resetting degraded mode when not in degraded mode."""
        self.validator.degraded_mode = False
        
        result = self.validator.reset_degraded_mode()
        
        self.assertFalse(result)
    
    def test_refresh_attempts_counter(self):
        """Test refresh attempts counter increments correctly."""
        now = int(time.time())
        token = CachedToken(
            access_token="count_test_token",
            token_type="Bearer",
            expires_at=now + 100,
            refresh_token="refresh_123",
            account_id="test-user"
        )
        self.mock_cache.tokens["test-provider:test-user"] = token
        
        # First attempt
        with patch.object(self.validator.cache, 'save_token', side_effect=Exception("Fail")):
            try:
                self.validator.validate_before_request("test-user", buffer_seconds=300)
            except:
                pass
        
        self.assertEqual(self.validator.refresh_attempts, 1)
        
        # Second attempt
        with patch.object(self.validator.cache, 'save_token', side_effect=Exception("Fail")):
            try:
                self.validator.validate_before_request("test-user", buffer_seconds=300)
            except:
                pass
        
        self.assertEqual(self.validator.refresh_attempts, 2)
    
    def test_notify_caine_degraded(self):
        """Test degraded mode notification to Caine."""
        # Mock file write
        with patch('builtins.open', create=True) as mock_open:
            mock_file = MagicMock()
            mock_open.return_value.__enter__.return_value = mock_file
            
            self.validator._notify_caine_degraded("test-user")
            
            # Verify alert file was written
            mock_file.write.assert_called_once()
            call_args = mock_file.write.call_args[0][0]
            self.assertIn("DEGRADED_MODE", call_args)
            self.assertIn("test-provider", call_args)
            self.assertIn("test-user", call_args)
    
    def test_initial_state(self):
        """Test validator initial state."""
        self.assertFalse(self.validator.degraded_mode)
        self.assertEqual(self.validator.refresh_attempts, 0)
        self.assertEqual(self.validator.max_refresh_attempts, 3)
        self.assertEqual(self.validator.provider, "test-provider")


class TestTokenValidatorIntegration(unittest.TestCase):
    """Integration tests for TokenValidator with real TokenCache."""
    
    @unittest.skipIf(
        'CI' in __import__('os').environ,
        "Skipping keychain integration test in CI"
    )
    def test_real_cache_operations(self):
        """Test with real macOS Keychain (manual run only)."""
        from src.auth.token_cache import TokenCache, CachedToken
        import time
        
        cache = TokenCache(app_name="test-validator-integration")
        
        validator = TokenValidator(cache, provider="integration-test")
        
        # Create and save a test token
        now = int(time.time())
        test_token = CachedToken(
            access_token="integration_test_token",
            token_type="Bearer",
            expires_at=now + 3600,
            refresh_token="integration_refresh",
            account_id="integration-user"
        )
        
        cache.save_token("integration-test", "integration-user", test_token)
        
        # Validate token
        result = validator.validate_before_request("integration-user")
        
        self.assertIsNotNone(result)
        self.assertEqual(result["access_token"], "integration_test_token")
        
        # Clean up
        cache.delete_token("integration-test", "integration-user")


if __name__ == '__main__':
    unittest.main()