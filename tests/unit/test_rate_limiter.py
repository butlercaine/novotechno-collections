"""
Unit tests for rate limiter module.
Tests token bucket rate limiting and exponential backoff.
"""

import unittest
import time
from unittest.mock import patch, MagicMock
from src.auth.rate_limiter import TokenBucketRateLimiter, ExponentialBackoff, RateLimitConfig


class TestRateLimitConfig(unittest.TestCase):
    """Test RateLimitConfig dataclass."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = RateLimitConfig()
        self.assertEqual(config.max_per_cycle, 20)
        self.assertEqual(config.cycle_seconds, 60)
        self.assertEqual(config.max_per_day, 100)
        self.assertEqual(config.day_seconds, 86400)
    
    def test_custom_config(self):
        """Test custom configuration values."""
        config = RateLimitConfig(
            max_per_cycle=10,
            cycle_seconds=30,
            max_per_day=50,
            day_seconds=43200
        )
        self.assertEqual(config.max_per_cycle, 10)
        self.assertEqual(config.cycle_seconds, 30)
        self.assertEqual(config.max_per_day, 50)
        self.assertEqual(config.day_seconds, 43200)


class TestTokenBucketRateLimiter(unittest.TestCase):
    """Test TokenBucketRateLimiter functionality."""
    
    def setUp(self):
        """Set up rate limiter for each test."""
        self.config = RateLimitConfig(
            max_per_cycle=20,
            cycle_seconds=60,
            max_per_day=100
        )
        self.limiter = TokenBucketRateLimiter(self.config)
    
    def test_acquire_within_limits(self):
        """Test acquiring tokens within rate limits."""
        # Should be able to acquire 20 tokens immediately (per-cycle limit)
        for i in range(20):
            self.assertTrue(self.limiter.try_acquire())
    
    def test_acquire_exceeds_cycle_limit(self):
        """Test exceeding per-cycle limit."""
        # Acquire 20 tokens (max per cycle)
        for _ in range(20):
            self.assertTrue(self.limiter.try_acquire())
        
        # 21st should fail (non-blocking)
        self.assertFalse(self.limiter.try_acquire())
    
    def test_blocking_acquire(self):
        """Test blocking acquisition waits for token availability."""
        # This test might be slow - reduced cycle time
        config = RateLimitConfig(cycle_seconds=1, max_per_cycle=2)
        limiter = TokenBucketRateLimiter(config)
        
        # Acquire all tokens
        limiter.acquire(block=True)
        limiter.acquire(block=True)
        
        # Blocking acquire should work after cycle resets
        start = time.time()
        result = limiter.acquire(block=True)
        elapsed = time.time() - start
        
        self.assertTrue(result)
        self.assertGreaterEqual(elapsed, 0.9)  # Should have waited ~1 second
    
    def test_daily_limit(self):
        """Test daily token limit."""
        # Acquire 100 tokens in batches to respect cycle limit
        acquired = 0
        for _ in range(5):  # 5 cycles
            for _ in range(20):  # 20 per cycle
                if self.limiter.try_acquire():
                    acquired += 1
            # Wait for cycle to reset
            if acquired < 100:
                time.sleep(0.1)  # Brief wait
        
        self.assertEqual(acquired, 100)
        
        # 101st should fail
        self.assertFalse(self.limiter.try_acquire())
        
        # Verify status shows daily limit exhausted
        status = self.limiter.get_status()
        self.assertEqual(status['daily_remaining'], 0)
    
    def test_success_criteria_21_emails(self):
        """Test success criteria: 21 emails should result in 20 sent."""
        # This simulates sending 21 emails with rate limiting
        emails_sent = 0
        emails_attempted = 21
        
        for i in range(emails_attempted):
            if self.limiter.try_acquire():
                emails_sent += 1
                # Simulate sending email
                # send_email(f"email_{i}@example.com", f"Message {i}")
        
        # Should only send 20 due to rate limit
        self.assertEqual(emails_sent, 20)
        self.assertLess(emails_sent, emails_attempted)
    
    def test_rate_limit_status(self):
        """Test getting rate limit status."""
        status = self.limiter.get_status()
        
        self.assertIn('daily_remaining', status)
        self.assertIn('daily_limit', status)
        self.assertIn('cycle_remaining', status)
        self.assertIn('cycle_limit', status)
        self.assertIn('cycle_window_age', status)
        self.assertIn('cycle_queue_size', status)
        
        self.assertEqual(status['daily_remaining'], 100)
        self.assertEqual(status['cycle_remaining'], 20)
        
        # Acquire some tokens
        for _ in range(5):
            self.limiter.acquire()
        
        status = self.limiter.get_status()
        self.assertEqual(status['daily_remaining'], 95)
        self.assertEqual(status['cycle_remaining'], 15)
        self.assertEqual(status['cycle_queue_size'], 5)
    
    def test_cycle_window_ages(self):
        """Test cycle window ages over time."""
        # First, acquire at least one token to set window_start
        self.limiter.try_acquire()
        
        start = time.time()
        status = self.limiter.get_status()
        
        age = status['cycle_window_age']
        self.assertGreaterEqual(age, 0)
        self.assertLess(age, 1.0)
        
        time.sleep(0.5)
        
        status = self.limiter.get_status()
        age = status['cycle_window_age']
        self.assertGreaterEqual(age, 0.5)
    
    def test_execute_with_rate_limit(self):
        """Test executing function with rate limiting."""
        mock_func = MagicMock(return_value="success")
        
        result = self.limiter.execute_with_rate_limit(mock_func, "arg1", kwarg1="kwarg1")
        
        self.assertEqual(result, "success")
        mock_func.assert_called_once_with("arg1", kwarg1="kwarg1")
    
    def test_thread_safety(self):
        """Test thread safety of rate limiter."""
        import threading
        
        tokens_acquired = 0
        lock = threading.Lock()
        
        def acquire_token():
            nonlocal tokens_acquired
            if self.limiter.try_acquire():
                with lock:
                    nonlocal tokens_acquired
                    tokens_acquired += 1
        
        # Spawn multiple threads trying to acquire
        threads = []
        for _ in range(30):
            t = threading.Thread(target=acquire_token)
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # Should have exactly 20 tokens (cycle limit)
        self.assertEqual(tokens_acquired, 20)
    
    def test_wait_for_token_timeout(self):
        """Test wait_for_token with timeout."""
        # Acquire all tokens
        for _ in range(20):
            self.limiter.acquire()
        
        start = time.time()
        result = self.limiter.wait_for_token(timeout=0.5)
        elapsed = time.time() - start
        
        self.assertFalse(result)  # Should timeout
        self.assertGreaterEqual(elapsed, 0.5)
        self.assertLess(elapsed, 1.0)


class TestExponentialBackoff(unittest.TestCase):
    """Test ExponentialBackoff functionality."""
    
    def test_initial_delay(self):
        """Test initial backoff delay."""
        backoff = ExponentialBackoff(base_delay=1.0, max_delay=60.0)
        
        delay = backoff.get_delay()
        self.assertEqual(delay, 1.0)  # First attempt
    
    def test_exponential_growth(self):
        """Test exponential delay growth."""
        backoff = ExponentialBackoff(base_delay=1.0, max_delay=60.0)
        
        delays = []
        for _ in range(5):
            delays.append(backoff.get_delay())
        
        # Should be approximately: 1, 2, 4, 8, 16
        expected = [1, 2, 4, 8, 16]
        for i, (actual, exp) in enumerate(zip(delays, expected)):
            self.assertEqual(actual, exp, f"Delay mismatch at attempt {i+1}")
    
    def test_max_delay_cap(self):
        """Test maximum delay cap."""
        backoff = ExponentialBackoff(base_delay=1.0, max_delay=10.0)
        
        # Get many delays to hit max
        delays = []
        for _ in range(10):
            delays.append(backoff.get_delay())
        
        # All delays should be <= max_delay
        for delay in delays:
            self.assertLessEqual(delay, 10.0)
        
        # Should eventually stay at max
        for _ in range(5):
            self.assertEqual(backoff.get_delay(), 10.0)
    
    def test_reset(self):
        """Test reset functionality."""
        backoff = ExponentialBackoff(base_delay=1.0, max_delay=60.0)
        
        # Get some delays
        for _ in range(3):
            backoff.get_delay()
        
        # Reset
        backoff.reset()
        
        # Should start over at base delay
        delay = backoff.get_delay()
        self.assertEqual(delay, 1.0)
    
    def test_sleeps_correct_duration(self):
        """Test that sleep actually waits."""
        backoff = ExponentialBackoff(base_delay=0.1, max_delay=1.0)
        
        start = time.time()
        backoff.sleep()
        elapsed = time.time() - start
        
        # Should sleep for approximately base_delay
        self.assertGreaterEqual(elapsed, 0.09)
        self.assertLess(elapsed, 0.2)
    
    def test_exponential_sleeps(self):
        """Test multiple sleeps with exponential growth."""
        backoff = ExponentialBackoff(base_delay=0.1, max_delay=1.0)
        
        delays = []
        for _ in range(4):
            start = time.time()
            backoff.sleep()
            elapsed = time.time() - start
            delays.append(round(elapsed, 1))
        
        # Should increase each time (with tolerance for timing)
        self.assertGreaterEqual(delays[1], delays[0])
        self.assertGreaterEqual(delays[2], delays[1])
        self.assertGreaterEqual(delays[2], delays[0] * 2)


class TestRateLimiterIntegration(unittest.TestCase):
    """Integration tests for rate limiter."""
    
    def test_rate_limiting_workflow(self):
        """Test complete rate limiting workflow."""
        config = RateLimitConfig(
            max_per_cycle=5,
            cycle_seconds=2,
            max_per_day=20
        )
        limiter = TokenBucketRateLimiter(config)
        
        # Use 3 tokens
        for _ in range(3):
            self.assertTrue(limiter.try_acquire())
        
        status = limiter.get_status()
        self.assertEqual(status['daily_remaining'], 17)
        self.assertEqual(status['cycle_remaining'], 2)
        
        # Use remaining 2 tokens
        for _ in range(2):
            self.assertTrue(limiter.try_acquire())
        
        # Should be at limit
        self.assertFalse(limiter.try_acquire())
    
    def test_429_backoff_integration(self):
        """Test rate limiter with exponential backoff for 429 responses."""
        limiter = TokenBucketRateLimiter()
        backoff = ExponentialBackoff(base_delay=0.1, max_delay=1.0)
        
        # Simulate 429 response
        hit_rate_limit = False
        
        def make_api_call():
            nonlocal hit_rate_limit
            if not limiter.try_acquire():
                hit_rate_limit = True
                raise Exception("Rate limited (429)")
            return "Success"
        
        # Exhaust tokens
        for _ in range(20):
            limiter.acquire()
        
        # Try API call
        try:
            make_api_call()
        except Exception:
            backoff.sleep()  # Wait
            # Retry (should succeed after cycle reset)
            time.sleep(0.5)  # Simulate waiting for cycle reset
            # Tokens should be available again after wait
            result = make_api_call()
            self.assertEqual(result, "Success")


if __name__ == '__main__':
    unittest.main()