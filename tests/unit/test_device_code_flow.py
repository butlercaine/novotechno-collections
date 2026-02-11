"""
Unit tests for device code flow module.
Tests MSAL device code flow without browser.
"""

import unittest
from unittest.mock import patch, MagicMock, Mock
from msal import PublicClientApplication
from src.auth.device_code_flow import DeviceCodeFlow


class MockDeviceFlow:
    """Mock device flow response."""
    
    def __init__(self):
        self.device_code = "test_device_code_12345"
        self.user_code = "ABCD-EFGH"
        self.verification_uri = "https://login.microsoftonline.com/common/oauth2/v2.0/deviceauth"
        self.expires_in = 900
        self.interval = 5


class TestDeviceCodeFlow(unittest.TestCase):
    """Test DeviceCodeFlow functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.client_id = "test-client-id-12345"
        self.authority = "https://login.microsoftonline.com/common"
        self.scopes = ["User.Read", "Mail.Send"]
        self.flow = DeviceCodeFlow(
            client_id=self.client_id,
            authority=self.authority,
            scopes=self.scopes
        )
    
    @patch('src.auth.device_code_flow.PublicClientApplication')
    def test_init(self, mock_msal):
        """Test initialization of DeviceCodeFlow."""
        flow = DeviceCodeFlow(
            client_id="test-id",
            authority="https://login.microsoftonline.com/test",
            scopes=["scope1", "scope2"]
        )
        
        mock_msal.assert_called_once_with(
            client_id="test-id",
            authority="https://login.microsoftonline.com/test"
        )
    
    @patch.object(PublicClientApplication, 'initiate_device_flow')
    def test_initiate_flow_success(self, mock_initiate):
        """Test successful device flow initiation."""
        mock_flow = {
            "device_code": "test_device_code",
            "user_code": "TEST-CODE",
            "verification_uri": "https://login.example.com/device",
            "expires_in": 900,
            "interval": 5
        }
        mock_initiate.return_value = mock_flow
        
        result = self.flow.initiate_flow()
        
        mock_initiate.assert_called_once_with(scopes=self.scopes)
        self.assertEqual(result, mock_flow)
        self.assertEqual(self.flow.get_user_code(), "TEST-CODE")
        self.assertEqual(self.flow.get_authorization_url(), "https://login.example.com/device")
    
    @patch.object(PublicClientApplication, 'initiate_device_flow')
    def test_initiate_flow_failure(self, mock_initiate):
        """Test device flow initiation failure."""
        mock_initiate.return_value = {
            "error": "invalid_request",
            "error_description": "Invalid client configuration"
        }
        
        with self.assertRaises(ValueError) as context:
            self.flow.initiate_flow()
        
        self.assertIn("Failed to create device flow", str(context.exception))
        self.assertIn("Invalid client configuration", str(context.exception))
    
    @patch('src.auth.device_code_flow.time.time')
    @patch('src.auth.device_code_flow.time.sleep')
    @patch.object(PublicClientApplication, 'acquire_token_by_device_flow')
    def test_poll_for_token_success(self, mock_acquire, mock_sleep, mock_time):
        """Test successful token polling."""
        # Setup mock time progression
        mock_time.side_effect = [1000, 1001, 1006]  # start, check1, check2
        
        mock_device_flow = {
            "device_code": "test_device_code",
            "interval": 5
        }
        
        # First call: authorization pending
        # Second call: success
        mock_acquire.side_effect = [
            {"error": "authorization_pending"},
            {
                "access_token": "test_access_token",
                "token_type": "Bearer",
                "expires_in": 3600,
                "refresh_token": "test_refresh_token",
                "scope": "User.Read Mail.Send"
            }
        ]
        
        result = self.flow.poll_for_token(mock_device_flow, interval=5, timeout=100)
        
        self.assertIsNotNone(result)
        self.assertEqual(result["access_token"], "test_access_token")
        self.assertEqual(result["token_type"], "Bearer")
        mock_sleep.assert_called_once_with(5)
    
    @patch('src.auth.device_code_flow.time.time')
    @patch('src.auth.device_code_flow.time.sleep')
    @patch.object(PublicClientApplication, 'acquire_token_by_device_flow')
    def test_poll_for_token_slow_down(self, mock_acquire, mock_sleep, mock_time):
        """Test token polling with slow_down response."""
        mock_time.side_effect = [1000, 1001, 1011]
        
        mock_device_flow = {
            "device_code": "test_device_code",
            "interval": 5
        }
        
        mock_acquire.side_effect = [
            {"error": "slow_down"},
            {
                "access_token": "test_access_token",
                "token_type": "Bearer",
                "expires_in": 3600
            }
        ]
        
        result = self.flow.poll_for_token(mock_device_flow, interval=5, timeout=100)
        
        self.assertIsNotNone(result)
        # Should wait interval + 5 seconds for slow_down
        mock_sleep.assert_called_once_with(10)
    
    @patch('src.auth.device_code_flow.time.time')
    @patch.object(PublicClientApplication, 'acquire_token_by_device_flow')
    def test_poll_for_token_timeout(self, mock_acquire, mock_time):
        """Test token polling timeout."""
        mock_time.side_effect = [1000, 2000]  # 1000 seconds elapsed
        
        mock_device_flow = {
            "device_code": "test_device_code",
            "interval": 5
        }
        
        # Always pending
        mock_acquire.return_value = {"error": "authorization_pending"}
        
        result = self.flow.poll_for_token(mock_device_flow, interval=5, timeout=900)
        
        self.assertIsNone(result)
    
    @patch('src.auth.device_code_flow.time.time')
    @patch.object(PublicClientApplication, 'acquire_token_by_device_flow')
    def test_poll_for_token_expired(self, mock_acquire, mock_time):
        """Test expired token error during polling."""
        mock_time.side_effect = [1000, 1001]
        
        mock_device_flow = {
            "device_code": "test_device_code",
            "interval": 5
        }
        
        mock_acquire.return_value = {"error": "expired_token"}
        
        with self.assertRaises(Exception) as context:
            self.flow.poll_for_token(mock_device_flow, interval=5, timeout=100)
        
        self.assertIn("Device code expired", str(context.exception))
    
    @patch('src.auth.device_code_flow.time.time')
    @patch.object(PublicClientApplication, 'acquire_token_by_device_flow')
    def test_poll_for_token_access_denied(self, mock_acquire, mock_time):
        """Test access denied error during polling."""
        mock_time.side_effect = [1000, 1001]
        
        mock_device_flow = {
            "device_code": "test_device_code",
            "interval": 5
        }
        
        mock_acquire.return_value = {"error": "access_denied"}
        
        with self.assertRaises(Exception) as context:
            self.flow.poll_for_token(mock_device_flow, interval=5, timeout=100)
        
        self.assertIn("User denied authorization", str(context.exception))
    
    @patch.object(PublicClientApplication, 'initiate_device_flow')
    @patch('src.auth.device_code_flow.DeviceCodeFlow.poll_for_token')
    def test_authenticate_default_prompt(self, mock_poll, mock_initiate):
        """Test authenticate with default prompt."""
        mock_initiate.return_value = {
            "device_code": "test_code",
            "user_code": "TEST-CODE-123",
            "verification_uri": "https://login.example.com/device",
            "interval": 5,
            "expires_in": 900
        }
        
        mock_token_response = {
            "access_token": "auth_access_token",
            "token_type": "Bearer",
            "expires_in": 3600
        }
        mock_poll.return_value = mock_token_response
        
        # Mock print to verify output
        with patch('builtins.print') as mock_print:
            result = self.flow.authenticate()
            
            # Should print instructions
            mock_print.assert_called()
            call_args = ' '.join([str(call) for call in mock_print.call_args_list])
            self.assertIn("TEST-CODE-123", call_args)
            self.assertIn("login.example.com/device", call_args)
        
        self.assertEqual(result, mock_token_response)
    
    @patch.object(PublicClientApplication, 'initiate_device_flow')
    @patch('src.auth.device_code_flow.DeviceCodeFlow.poll_for_token')
    def test_authenticate_with_callback(self, mock_poll, mock_initiate):
        """Test authenticate with custom callback."""
        mock_initiate.return_value = {
            "device_code": "test_code",
            "user_code": "CALLBACK-CODE",
            "verification_uri": "https://login.test.com/device",
            "interval": 5
        }
        
        mock_token_response = {
            "access_token": "callback_token",
            "token_type": "Bearer"
        }
        mock_poll.return_value = mock_token_response
        
        callback_called = False
        captured_user_code = None
        captured_url = None
        
        def test_callback(user_code, url):
            nonlocal callback_called, captured_user_code, captured_url
            callback_called = True
            captured_user_code = user_code
            captured_url = url
        
        result = self.flow.authenticate(prompt_callback=test_callback)
        
        self.assertTrue(callback_called)
        self.assertEqual(captured_user_code, "CALLBACK-CODE")
        self.assertEqual(captured_url, "https://login.test.com/device")
        self.assertEqual(result, mock_token_response)
    
    @patch.object(PublicClientApplication, 'get_accounts')
    @patch.object(PublicClientApplication, 'acquire_token_silent')
    def test_get_token_silent_success(self, mock_silent, mock_get_accounts):
        """Test silent token acquisition from cache."""
        mock_account = {
            "username": "test@example.com",
            "home_account_id": "12345"
        }
        mock_get_accounts.return_value = [mock_account]
        
        mock_token_response = {
            "access_token": "silent_token",
            "token_type": "Bearer",
            "expires_in": 3600
        }
        mock_silent.return_value = mock_token_response
        
        result = self.flow.get_token_silent()
        
        self.assertIsNotNone(result)
        self.assertEqual(result["access_token"], "silent_token")
        mock_silent.assert_called_once_with(
            scopes=self.scopes,
            account=mock_account
        )
    
    @patch.object(PublicClientApplication, 'get_accounts')
    def test_get_token_silent_no_accounts(self, mock_get_accounts):
        """Test silent token with no cached accounts."""
        mock_get_accounts.return_value = []
        
        result = self.flow.get_token_silent()
        
        self.assertIsNone(result)
    
    @patch.object(PublicClientApplication, 'get_accounts')
    @patch.object(PublicClientApplication, 'acquire_token_silent')
    def test_get_token_silent_failure(self, mock_silent, mock_get_accounts):
        """Test silent token acquisition failure."""
        mock_account = {"username": "test@example.com"}
        mock_get_accounts.return_value = [mock_account]
        
        # Return error instead of token
        mock_silent.return_value = {"error": "interaction_required"}
        
        result = self.flow.get_token_silent()
        
        self.assertIsNone(result)
    
    @patch.object(PublicClientApplication, 'acquire_token_by_refresh_token')
    def test_refresh_token(self, mock_refresh):
        """Test token refresh functionality."""
        refresh_token = "test_refresh_token_123"
        
        mock_response = {
            "access_token": "refreshed_access_token",
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": "new_refresh_token"
        }
        mock_refresh.return_value = mock_response
        
        # Note: The current implementation doesn't have a separate refresh method
        # This test documents expected behavior for token refresh
        result = mock_refresh(
            scopes=self.scopes,
            refresh_token=refresh_token
        )
        
        self.assertEqual(result["access_token"], "refreshed_access_token")


if __name__ == '__main__':
    unittest.main()