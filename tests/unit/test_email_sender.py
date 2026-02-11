"""
Unit tests for Graph API email sender module.
Tests email sending, rate limiting, and error handling.
"""

import unittest
import time
from unittest.mock import MagicMock, patch, Mock
from requests.exceptions import HTTPError, Timeout
from src.collections.email_sender import GraphEmailSender, RateLimitExceeded
from src.auth.token_validator import TokenValidator
from src.auth.rate_limiter import TokenBucketRateLimiter
from src.auth.token_cache import CachedToken, TokenCache


class MockTokenValidator:
    """Mock token validator for testing."""
    
    def __init__(self, token_response=None):
        self.token_response = token_response or {
            "access_token": "mock_token_123",
            "token_type": "Bearer",
            "expires_in": 3600
        }
        self.validate_count = 0
        # Add cache attribute to match real interface
        self.cache = None
        # Add status tracking
        self._degraded_mode = False
        self._refresh_attempts = 0
    
    def validate_before_request(self, account_id, buffer_seconds=300):
        self.validate_count += 1
        return self.token_response
    
    def get_status(self, account_id):
        """Mock get_status method."""
        return {
            "account_id": account_id,
            "status": "DEGRADED" if self._degraded_mode else "ACTIVE",
            "degraded_mode": self._degraded_mode,
            "refresh_attempts": self._refresh_attempts
        }


class TestGraphEmailSender(unittest.TestCase):
    """Test GraphEmailSender functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_validator = MockTokenValidator()
        self.mock_limiter = TokenBucketRateLimiter()
        self.account_id = "test-account"
    
    def test_send_email_success(self):
        """Test successful email sending."""
        # Mock validator and rate limiter
        validator = MockTokenValidator()
        limiter = TokenBucketRateLimiter()
        
        sender = GraphEmailSender(
            token_validator=validator,
            rate_limiter=limiter,
            account_id=self.account_id
        )
        
        # Mock the session post
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.headers = {"Message-ID": "msg-12345"}
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(sender.session, 'post', return_value=mock_response):
            result = sender.send_email(
                to_address="recipient@example.com",
                subject="Test Subject",
                body_html="<p>Test body</p>"
            )
        
        self.assertEqual(result["status"], "sent")
        self.assertEqual(result["message_id"], "msg-12345")
        self.assertEqual(result["recipient"], "recipient@example.com")
        self.assertEqual(result["attempts"], 1)
    
    def test_send_email_with_cc(self):
        """Test email sending with CC recipients."""
        validator = MockTokenValidator()
        limiter = TokenBucketRateLimiter()
        
        sender = GraphEmailSender(
            token_validator=validator,
            rate_limiter=limiter,
            account_id=self.account_id
        )
        
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.headers = {"Message-ID": "msg-cc-test"}
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(sender.session, 'post', return_value=mock_response) as mock_post:
            result = sender.send_email(
                to_address="recipient@example.com",
                subject="Test with CC",
                body_html="<p>Test</p>",
                cc_addresses=["cc1@example.com", "cc2@example.com"]
            )
        
        self.assertEqual(result["status"], "sent")
        
        # Verify CC was included in request
        call_args = mock_post.call_args
        email_data = call_args[1]["json"]["message"]
        self.assertEqual(len(email_data["ccRecipients"]), 2)
    
    def test_send_email_rate_limited(self):
        """Test email sending when rate limited."""
        validator = MockTokenValidator()
        
        # Create limiter with 0 tokens
        limiter = TokenBucketRateLimiter()
        for _ in range(20):
            limiter.try_acquire()  # Drain all tokens
        
        sender = GraphEmailSender(
            token_validator=validator,
            rate_limiter=limiter,
            account_id=self.account_id
        )
        
        with self.assertRaises(RateLimitExceeded) as context:
            sender.send_email(
                to_address="rate-limited@example.com",
                subject="Test",
                body_html="<p>Test</p>"
            )
        
        self.assertIn("Rate limit exceeded", str(context.exception))
    
    def test_send_email_429_retry(self):
        """Test email retry on 429 response."""
        validator = MockTokenValidator()
        limiter = TokenBucketRateLimiter()
        
        sender = GraphEmailSender(
            token_validator=validator,
            rate_limiter=limiter,
            account_id=self.account_id
        )
        
        # First call returns 429, second succeeds
        mock_429_response = MagicMock()
        mock_429_response.status_code = 429
        mock_429_response.raise_for_status = MagicMock(
            side_effect=HTTPError(response=mock_429_response)
        )
        
        mock_success_response = MagicMock()
        mock_success_response.status_code = 202
        mock_success_response.headers = {"Message-ID": "msg-retry-success"}
        mock_success_response.raise_for_status = MagicMock()
        
        with patch.object(sender.session, 'post', side_effect=[
            mock_429_response,
            mock_success_response
        ]):
            result = sender.send_email(
                to_address="retry@example.com",
                subject="Retry Test",
                body_html="<p>Test</p>"
            )
        
        self.assertEqual(result["status"], "sent")
        self.assertEqual(result["attempts"], 2)
    
    def test_send_email_401_unauthorized(self):
        """Test email sending with 401 unauthorized."""
        validator = MockTokenValidator()
        limiter = TokenBucketRateLimiter()
        
        sender = GraphEmailSender(
            token_validator=validator,
            rate_limiter=limiter,
            account_id=self.account_id
        )
        
        mock_401_response = MagicMock()
        mock_401_response.status_code = 401
        mock_401_response.text = "Token expired"
        mock_401_response.raise_for_status = MagicMock(
            side_effect=HTTPError(response=mock_401_response)
        )
        
        with patch.object(sender.session, 'post', return_value=mock_401_response):
            with self.assertRaises(Exception) as context:
                sender.send_email(
                    to_address="unauthorized@example.com",
                    subject="Test",
                    body_html="<p>Test</p>"
                )
        
        self.assertIn("Authentication failed", str(context.exception))
    
    def test_send_email_403_forbidden(self):
        """Test email sending with 403 forbidden."""
        validator = MockTokenValidator()
        limiter = TokenBucketRateLimiter()
        
        sender = GraphEmailSender(
            token_validator=validator,
            rate_limiter=limiter,
            account_id=self.account_id
        )
        
        mock_403_response = MagicMock()
        mock_403_response.status_code = 403
        mock_403_response.text = "Permission denied"
        mock_403_response.raise_for_status = MagicMock(
            side_effect=HTTPError(response=mock_403_response)
        )
        
        with patch.object(sender.session, 'post', return_value=mock_403_response):
            with self.assertRaises(Exception) as context:
                sender.send_email(
                    to_address="forbidden@example.com",
                    subject="Test",
                    body_html="<p>Test</p>"
                )
        
        self.assertIn("Permission denied", str(context.exception))
    
    def test_send_collection_reminder(self):
        """Test collection reminder email with template."""
        validator = MockTokenValidator()
        limiter = TokenBucketRateLimiter()
        
        sender = GraphEmailSender(
            token_validator=validator,
            rate_limiter=limiter,
            account_id=self.account_id
        )
        
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.headers = {"Message-ID": "msg-collection-123"}
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(sender.session, 'post', return_value=mock_response) as mock_post:
            result = sender.send_collection_reminder(
                to_address="debtor@example.com",
                debtor_name="John Doe",
                amount=1500.00,
                due_date="2026-03-15",
                collection_id="COLL-2026-001"
            )
        
        self.assertEqual(result["status"], "sent")
        
        # Verify email content
        call_args = mock_post.call_args
        email_data = call_args[1]["json"]["message"]
        
        self.assertIn("COLL-2026-001", email_data["subject"])
        self.assertIn("John Doe", email_data["body"]["content"])
        self.assertIn("$1,500.00", email_data["body"]["content"])
        self.assertIn("2026-03-15", email_data["body"]["content"])
    
    def test_retry_exponential_backoff_timing(self):
        """Test that exponential backoff waits 1s, 2s, 4s."""
        validator = MockTokenValidator()
        limiter = TokenBucketRateLimiter()
        
        sender = GraphEmailSender(
            token_validator=validator,
            rate_limiter=limiter,
            account_id=self.account_id
        )
        
        # All attempts return 429
        mock_429_response = MagicMock()
        mock_429_response.status_code = 429
        mock_429_response.raise_for_status = MagicMock(
            side_effect=HTTPError(response=mock_429_response)
        )
        
        with patch.object(sender.session, 'post', return_value=mock_429_response):
            with patch('time.sleep') as mock_sleep:
                with self.assertRaises(Exception):
                    sender.send_email(
                        to_address="backoff@example.com",
                        subject="Test",
                        body_html="<p>Test</p>"
                    )
        
        # Should have slept 3 times: 1s + 2s + 4s = 7s total
        self.assertEqual(mock_sleep.call_count, 3)
        
        # Verify backoff timing
        calls = mock_sleep.call_args_list
        self.assertEqual(calls[0][0][0], 1)  # 1 second
        self.assertEqual(calls[1][0][0], 2)  # 2 seconds
        self.assertEqual(calls[2][0][0], 4)  # 4 seconds
    
    def test_max_retry_attempts(self):
        """Test that retries stop after max_attempts."""
        validator = MockTokenValidator()
        limiter = TokenBucketRateLimiter()
        
        sender = GraphEmailSender(
            token_validator=validator,
            rate_limiter=limiter,
            account_id=self.account_id
        )
        
        # All attempts return 429
        mock_429_response = MagicMock()
        mock_429_response.status_code = 429
        mock_429_response.raise_for_status = MagicMock(
            side_effect=HTTPError(response=mock_429_response)
        )
        
        with patch.object(sender.session, 'post', return_value=mock_429_response):
            with patch('time.sleep'):
                with self.assertRaises(Exception) as context:
                    sender.send_email(
                        to_address="max-retries@example.com",
                        subject="Test",
                        body_html="<p>Test</p>"
                    )
        
        self.assertIn("Failed to send email", str(context.exception))
        # Should have attempted 3 times
        self.assertEqual(sender.session.post.call_count, 3)
    
    def test_check_rate_limit_status(self):
        """Test rate limit status check."""
        validator = MockTokenValidator()
        limiter = TokenBucketRateLimiter()
        
        # Use one token
        limiter.try_acquire()
        
        sender = GraphEmailSender(
            token_validator=validator,
            rate_limiter=limiter,
            account_id=self.account_id
        )
        
        status = sender.check_rate_limit_status()
        
        self.assertIn('daily_remaining', status)
        self.assertIn('cycle_remaining', status)
        self.assertEqual(status['cycle_remaining'], 19)  # 1 used
    
    def test_get_sending_stats(self):
        """Test getting sending statistics."""
        validator = MockTokenValidator()
        limiter = TokenBucketRateLimiter()
        
        sender = GraphEmailSender(
            token_validator=validator,
            rate_limiter=limiter,
            account_id=self.account_id
        )
        
        stats = sender.get_sending_stats()
        
        self.assertIn('rate_limit_status', stats)
        self.assertIn('validator_status', stats)
        self.assertEqual(stats['account'], self.account_id)
        self.assertIn('timestamp', stats)
    
    def test_session_headers_set(self):
        """Test that session headers are set correctly."""
        validator = MockTokenValidator(token_response={
            "access_token": "my_token_123",
            "token_type": "Bearer",
            "expires_in": 3600
        })
        limiter = TokenBucketRateLimiter()
        
        sender = GraphEmailSender(
            token_validator=validator,
            rate_limiter=limiter,
            account_id=self.account_id
        )
        
        self.assertEqual(sender.session.headers["Content-Type"], "application/json")
    
    def test_update_session_auth(self):
        """Test updating session authorization."""
        validator = MockTokenValidator()
        limiter = TokenBucketRateLimiter()
        
        sender = GraphEmailSender(
            token_validator=validator,
            rate_limiter=limiter,
            account_id=self.account_id
        )
        
        sender._update_session_auth("new_access_token_xyz")
        
        self.assertEqual(
            sender.session.headers["Authorization"],
            "Bearer new_access_token_xyz"
        )
    
    def test_request_timeout(self):
        """Test that requests timeout after 30 seconds."""
        validator = MockTokenValidator()
        limiter = TokenBucketRateLimiter()
        
        sender = GraphEmailSender(
            token_validator=validator,
            rate_limiter=limiter,
            account_id=self.account_id
        )
        
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.headers = {"Message-ID": "msg-timeout"}
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(sender.session, 'post', return_value=mock_response) as mock_post:
            sender.send_email(
                to_address="timeout@example.com",
                subject="Test",
                body_html="<p>Test</p>"
            )
        
        # Verify timeout was passed
        call_kwargs = mock_post.call_args[1]
        self.assertEqual(call_kwargs['timeout'], 30)


class TestRateLimitExceeded(unittest.TestCase):
    """Test RateLimitExceeded exception."""
    
    def test_exception_message(self):
        """Test exception message."""
        exc = RateLimitExceeded("Rate limit exceeded")
        self.assertEqual(str(exc), "Rate limit exceeded")
    
    def test_exception_inheritance(self):
        """Test that RateLimitExceeded is an Exception."""
        exc = RateLimitExceeded("Test")
        self.assertIsInstance(exc, Exception)


if __name__ == '__main__':
    unittest.main()