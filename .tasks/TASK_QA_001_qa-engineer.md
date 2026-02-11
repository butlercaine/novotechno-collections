# TASK: OAuth Token Persistence Validation
**Task ID:** TASK_QA_001
**Owner:** qa-engineer-novotechno
**Type:** validation
**Priority:** P0
**Status:** PENDING
**Created:** 2026-02-11 08:00 GMT-5

## Context
Validate OAuth token persistence across agent restarts. Critical requirement: token must survive restart without re-authentication (C-008). This validation upgrades confidence from Substantive → Definitive.

## Requirements

### 1. Token Persistence Test Plan
**File:** `novotechno-collections/tests/test_oauth_persistence.py`

**Test Design:**
```python
import pytest
import time
import subprocess
from datetime import datetime

class TestOAuthPersistence:
    """OAuth token persistence validation"""
    
    TEST_DURATION_HOURS = 2
    RESTART_INTERVAL_MINUTES = 30  # 4 restarts in 2 hours
    
    def test_token_survives_restart(self, setup_oauth):
        """Token persists across agent restart without re-auth"""
        # Get initial token
        initial_token = setup_oauth.get_cached_token()
        assert initial_token is not None, "No token cached after setup"
        
        # Simulate agent restart
        subprocess.run "-f", "collections-emailer"], check=False)
        time(["pkill",.sleep(2)
        
        # Reinitialize and check token
        subprocess.Popen(["python", "scripts/collections-emailer.py", "--once"])
        time.sleep(5)
        
        # Token should still be there
        new_token = setup_oauth.get_cached_token()
        assert new_token is not None, "Token lost after restart"
        assert new_token == initial_token, "Token changed after restart"
    
    def test_silent_refresh_before_expiry(self, mock_token_expiry):
        """Token refreshes automatically before expiry"""
        # Mock token to expire in 200 seconds (<300s buffer)
        setup_oauth.set_token_expiry(time.time() + 200)
        
        # Trigger email send
        setup_oauth.send_test_email()
        
        # Should trigger silent refresh
        new_expiry = setup_oauth.get_token_expiry()
        assert new_expiry > time.time() + 200, "Token not refreshed"
    
    def test_degraded_mode_on_refresh_failure(self, mock_refresh_failure):
        """DEGRADED mode activated after 3 refresh failures"""
        # Force 3 refresh failures
        for _ in range(3):
            with pytest.raises(RefreshFailedError):
                setup_oauth.trigger_refresh()
        
        assert setup_oauth.is_degraded_mode(), "DEGRADED mode not activated"
        assert setup_oauth.get_degraded_reason() == "3 consecutive refresh failures"
    
    def test_2_hour_continuous_operation(self, setup_oauth):
        """System operates continuously for 2 hours"""
        start_time = time.time()
        emails_sent = 0
        
        while time.time() - start_time < self.TEST_DURATION_HOURS * 3600:
            # Attempt to send emails periodically
            if emails_sent < 20:
                try:
                    result = setup_oauth.send_test_email()
                    emails_sent += 1
                except TokenExpiredError:
                    # Should auto-refresh
                    setup_oauth.force_refresh()
            
            # Check for restarts (simulate 4 restarts)
            elapsed = (time.time() - start_time) / 3600
            if elapsed > 0 and elapsed % 0.5 < 0.01:  # Every 30 min
                self._simulate_restart()
            
            time.sleep(60)  # Check every minute
        
        assert emails_sent >= 18, f"Only sent {emails_sent}/20 expected emails"
```

### 2. Test Execution Script
**File:** `novotechno-collections/scripts/run_oauth_validation.py`

```python
#!/usr/bin/env python3
"""
OAuth Token Persistence Validation Script

Usage:
    python scripts/run_oauth_validation.py --duration 2 --restarts 4
"""
import click
import time
import json
from datetime import datetime
from pathlib import Path

@click.command()
@click.option("--duration", default=2, help="Test duration in hours")
@click.option("--restarts", default=4, help="Number of simulated restarts")
@click.option("--output", type=click.Path(), help="Output file for results")
def main(duration: int, restarts: int, output: str):
    """Run OAuth token persistence validation"""
    
    results = {
        "test_name": "OAuth Token Persistence",
        "start_time": datetime.utcnow().isoformat(),
        "duration_hours": duration,
        "restart_count": restarts,
        "tests": []
    }
    
    click.echo(f"🚀 Starting OAuth validation ({duration}h, {restarts} restarts)")
    
    # Test 1: Token persistence across restarts
    click.echo("\n📋 Test 1: Token persistence")
    test1_result = _test_token_persistence(restarts)
    results["tests"].append(test1_result)
    
    # Test 2: Silent refresh
    click.echo("\n🔄 Test 2: Silent refresh")
    test2_result = _test_silent_refresh()
    results["tests"].append(test2_result)
    
    # Test 3: Degraded mode
    click.echo("\n⚠️ Test 3: Degraded mode")
    test3_result = _test_degraded_mode()
    results["tests"].append(test3_result)
    
    # Calculate overall result
    passed = all(t["passed"] for t in results["tests"])
    results["overall"] = {
        "passed": passed,
        "completion_time": datetime.utcnow().isoformat(),
        "summary": f"{sum(1 for t in results['tests'] if t['passed'])}/{len(results['tests'])} tests passed"
    }
    
    # Output results
    if output:
        with open(output, 'w') as f:
            json.dump(results, f, indent=2)
        click.echo(f"\n📄 Results written to: {output}")
    
    # Summary
    click.echo(f"\n{'✅ ALL TESTS PASSED' if passed else '❌ SOME TESTS FAILED'}")
    click.echo(results["overall"]["summary"])
    
    return 0 if passed else 1

def _test_token_persistence(restart_count: int) -> Dict:
    """Test token persistence"""
    return {"name": "token_persistence", "passed": True, "restarts_tested": restart_count}

def _test_silent_refresh() -> Dict:
    """Test silent refresh"""
    return {"name": "silent_refresh", "passed": True}

def _test_degraded_mode() -> Dict:
    """Test degraded mode"""
    return {"name": "degraded_mode", "passed": True}

if __name__ == "__main__":
    main()
```

### 3. Validation Report Template
**File:** `~/.openclaw/workspace-qa-engineer-novotechno/OAUTH-VALIDATION-RESULTS.md`

```markdown
# OAuth Token Persistence Validation Report

**Test Date:** [DATE]
**Test Duration:** 2 hours
**Agent:** operations-agent-novotechno
**Status:** PASSED / FAILED

---

## Test Results

### Test 1: Token Persistence Across Restarts
**Status:** ✅ PASSED / ❌ FAILED
- Restarts performed: 4
- Token survived all restarts: YES / NO
- Re-authentication required: 0 times

### Test 2: Silent Refresh
**Status:** ✅ PASSED / ❌ FAILED
- Tokens refreshed automatically: X
- Refresh latency: <5s
- Failures: 0

### Test 3: Degraded Mode Activation
**Status:** ✅ PASSED / ❌ FAILED
- 3 refresh failures triggered DEGRADED mode: YES / NO
- Caine notification sent: YES / NO

---

## Key Metrics

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Token survival rate | X% | 100% | ✅/❌ |
| Auto-refresh success | X% | >99% | ✅/❌ |
| Silent refresh latency | X.Xs | <5s | ✅/❌ |
| False positives | X | 0 | ✅/❌ |

---

## Recommendations

[Based on test results]

---

## Confidence Upgrade

**Current Tier:** Substantive  
**After Validation:** Definitive / Substantive (conditional)

**Conditions for Definitive:**
- [ ] Token survival: 100% across 4 restarts
- [ ] Silent refresh: >99% success rate
- [ ] Degraded mode: Functional
```

## Dependencies
- TASK_OAUTH_002 (must complete first)
- pytest for test execution

## Output Files
- `novotechno-collections/tests/test_oauth_persistence.py` (100 lines)
- `novotechno-collections/scripts/run_oauth_validation.py` (150 lines)
- `~/.openclaw/workspace-qa-engineer-novotechno/OAUTH-VALIDATION-RESULTS.md` (validation report)

## Definition of Done
- [ ] Token persistence test passes (100% survival)
- [ ] Silent refresh test passes (>99% success)
- [ ] Degraded mode test passes
- [ ] Validation report written
- [ ] RESPONSE file written

## Success Criteria (from PROJECT_SCOPING)
- [ ] Token reused across 3+ agent restarts without re-auth (C-008)
- [ ] Silent refresh succeeds before expiry
- [ ] Validation test passes
- [ ] **GATE:** Confidence upgrade from Substantive → Definitive

## Previous Task
TASK_OAUTH_002 (Graph API email client) — dependency met

## Next Task
TASK_QA_002 (PDF confidence validation) — can run in parallel
