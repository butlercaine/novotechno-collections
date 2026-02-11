import sys
import os

# Add parent directory to path to import src modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import unittest
import time
from unittest.mock import patch, MagicMock
from src.auth.rate_limiter import TokenBucketRateLimiter, ExponentialBackoff, RateLimitConfig

# Run tests
if __name__ == '__main__':
    loader = unittest.TestLoader()
    
    # Run specific test that failed
    suite = loader.loadTestsFromName('test_rate_limiter.TestTokenBucketRateLimiter.test_daily_limit')
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    if result.wasSuccessful():
        print("\n✅ test_daily_limit PASSED")
    else:
        print(f"\n❌ test_daily_limit FAILED: {result.failures}")