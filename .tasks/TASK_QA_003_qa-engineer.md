# TASK: E2E Integration Testing
**Task ID:** TASK_QA_003
**Owner:** qa-engineer-novotechno
**Type:** validation
**Priority:** P0
**Status:** PENDING
**Created:** 2026-02-11 08:00 GMT-5

## Context
Run comprehensive end-to-end testing of the full payment cycle: PDF → Reminder Email → Payment Detection → State Update → Archive.

## Requirements

### 1. E2E Test Scenarios
**File:** `novotechno-collections/tests/test_e2e.py`

```python
"""
End-to-End Integration Tests

Tests the complete collections workflow:
1. Invoice PDF arrives → parsed → state created
2. Reminder email scheduled → sent
3. Payment detected → state updated → archived
4. Supervisor validates end-to-end
"""
import pytest
import time
import json
from pathlib import Path
from datetime import datetime

class TestFullPaymentCycle:
    """End-to-end payment cycle tests"""
    
    @pytest.fixture
    def test_invoice(self, tmp_path):
        """Create test invoice PDF"""
        invoice_path = tmp_path / "test_invoice.pdf"
        # Create minimal PDF for testing
        return invoice_path
    
    @pytest.fixture
    def test_payment(self, tmp_path):
        """Create payment confirmation"""
        payment_path = tmp_path / "payment_confirmation.pdf"
        return payment_path
    
    def test_full_cycle_invoice_to_archive(self, test_invoice, test_payment, 
                                          collections_system):
        """Test complete payment cycle from invoice to archive"""
        
        # Step 1: Invoice arrives
        invoice_data = {
            "invoice_number": "E2E-TEST-001",
            "client": "test-client",
            "amount": 1500.00,
            "due_date": (datetime.now() + timedelta(days=3)).isoformat(),
            "email": "test@example.com"
        }
        
        # Simulate invoice arrival
        collections_system.inject_invoice(test_invoice, invoice_data)
        
        # Verify state created
        state = collections_system.get_state("test-client", "E2E-TEST-001")
        assert state["status"] == "unpaid"
        assert state["confidence"] >= 0.85
        
        # Step 2: Reminder scheduled
        collections_system.trigger_scheduler()
        pending = collections_system.get_pending_emails()
        assert any(e["invoice"] == "E2E-TEST-001" for e in pending)
        
        # Step 3: Payment arrives
        collections_system.inject_payment(test_payment, {
            "invoice": "E2E-TEST-001",
            "amount": 1500.00,
            "method": "bank_transfer"
        })
        
        # Step 4: State updated
        state = collections_system.get_state("test-client", "E2E-TEST-001")
        assert state["status"] == "paid"
        assert state["paid_at"] is not None
        
        # Step 5: Archived
        archive = collections_system.get_archive("test-client", "E2E-TEST-001")
        assert archive is not None
        assert archive["status"] == "paid"
        
        # Step 6: Supervisor validates
        health = collections_system.run_health_check()
        assert health["consistent"]
        
        return True
    
    def test_error_handling_oauth_failure(self, collections_system, mock_oauth_failure):
        """Test graceful handling of OAuth failures"""
        
        # Force OAuth failure
        collections_system.set_oauth_mode("failure")
        
        # Attempt to send email
        result = collections_system.send_reminder("test-invoice")
        
        # Should handle gracefully
        assert result["status"] == "degraded"
        assert collections_system.get_degraded_count() == 1
    
    def test_error_handling_pdf_parse_failure(self, collections_system, corrupt_pdf):
        """Test handling of unparseable PDF"""
        
        # Inject corrupt PDF
        collections_system.inject_invoice(corrupt_pdf, {"invoice": "CORRUPT-001"})
        
        # Should queue for manual review
        manual_queue = collections_system.get_manual_queue()
        assert any(q["invoice"] == "CORRUPT-001" for q in manual_queue)
    
    def test_permission_denied_handling(self, collections_system, restricted_dir):
        """Test handling of filesystem permission errors"""
        
        # Attempt to scan restricted directory
        result = collections_system.scan_directory(restricted_dir)
        
        # Should escalate gracefully
        assert result["status"] == "permission_denied"
        assert len(result["escalations"]) == 1
    
    def test_supervisor_recovery_after_crash(self, collections_system, simulate_crash):
        """Test supervisor detects and recovers from crash"""
        
        # Simulate agent crash
        simulate_crash("collections-emailer")
        
        # Supervisor should detect
        health = collections_system.run_health_check()
        assert health["agents"]["collections-emailer"]["status"] == "down"
        
        # Recovery should be attempted
        recovery = collections_system.attempt_recovery()
        assert recovery["restarted"] == True
    
    def test_rate_limit_respect(self, collections_system):
        """Test that rate limits are enforced"""
        
        # Attempt 25 emails (limit is 20)
        results = []
        for i in range(25):
            result = collections_system.send_reminder(f"invoice-{i}")
            results.append(result)
        
        # Should respect limit
        sent = sum(1 for r in results if r["status"] == "sent")
        rate_limited = sum(1 for r in results if r["status"] == "rate_limited")
        
        assert sent == 20
        assert rate_limited == 5
```

### 2. E2E Test Runner
**File:** `novotechno-collections/scripts/run_e2e_tests.py`

```python
#!/usr/bin/env python3
"""
End-to-End Test Runner

Usage:
    python scripts/run_e2e_tests.py --output results.json
"""
import click
import json
import time
from datetime import datetime
from pathlib import Path

@click.command()
@click.option("--output", type=click.Path(), help="Output file for results")
@click.option("--verbose", is_flag=True, help="Verbose output")
def main(output: str, verbose: bool):
    """Run end-to-end integration tests"""
    
    results = {
        "test_name": "E2E Integration Testing",
        "start_time": datetime.utcnow().isoformat(),
        "scenarios": []
    }
    
    click.echo("🚀 Starting E2E Integration Tests\n")
    
    # Test scenarios
    scenarios = [
        ("Full Payment Cycle", "test_full_cycle_invoice_to_archive"),
        ("OAuth Failure Handling", "test_error_handling_oauth_failure"),
        ("PDF Parse Failure", "test_error_handling_pdf_parse_failure"),
        ("Permission Denied", "test_permission_denied_handling"),
        ("Crash Recovery", "test_supervisor_recovery_after_crash"),
        ("Rate Limit Respect", "test_rate_limit_respect"),
    ]
    
    passed = 0
    failed = 0
    
    for scenario_name, test_func in scenarios:
        click.eprint(f"📋 {scenario_name}...")
        
        try:
            # Run test (simplified - would use pytest in practice)
            result = _run_test(test_func)
            
            if result["passed"]:
                click.eprint(f"  ✅ PASSED")
                passed += 1
            else:
                click.eprint(f"  ❌ FAILED: {result.get('error', 'Unknown')}")
                failed += 1
            
            results["scenarios"].append({
                "name": scenario_name,
                "passed": result["passed"],
                "duration_seconds": result.get("duration", 0),
                "error": result.get("error")
            })
            
        except Exception as e:
            click.eprint(f"  ❌ ERROR: {e}")
            failed += 1
            results["scenarios"].append({
                "name": scenario_name,
                "passed": False,
                "error": str(e)
            })
    
    # Summary
    results["summary"] = {
        "total": len(scenarios),
        "passed": passed,
        "failed": failed,
        "completion_time": datetime.utcnow().isoformat(),
        "success_rate": f"{passed}/{len(scenarios)} ({passed/len(scenarios)*100:.0f}%)"
    }
    
    click.eprint(f"\n{'✅ ALL TESTS PASSED' if failed == 0 else f'❌ {failed} TEST(S) FAILED'}")
    click.eprint(f"Success Rate: {results['summary']['success_rate']}")
    
    # Output results
    if output:
        with open(output, 'w') as f:
            json.dump(results, f, indent=2)
        click.eprint(f"\n📄 Results: {output}")
    
    return 0 if failed == 0 else 1

def _run_test(test_func: str) -> Dict:
    """Run individual test (simplified)"""
    # In practice, would use pytest to run actual tests
    return {"passed": True, "duration": 5.0}

if __name__ == "__main__":
    main()
```

### 3. E2E Test Results Template
**File:** `~/.openclaw/workspace-qa-engineer-novotechno/E2E-TEST-RESULTS.md`

```markdown
# E2E Integration Test Results

**Date:** [DATE]
**Duration:** 2 hours
**Tester:** qa-engineer-novotechno
**Status:** PASSED / FAILED

---

## Test Summary

| Scenario | Status | Duration | Notes |
|----------|--------|----------|-------|
| Full Payment Cycle | ✅ PASS / ❌ FAIL | X min | |
| OAuth Failure Handling | ✅ PASS / ❌ FAIL | X min | |
| PDF Parse Failure | ✅ PASS / ❌ FAIL | X min | |
| Permission Denied | ✅ PASS / ❌ FAIL | X min | |
| Crash Recovery | ✅ PASS / ❌ FAIL | X min | |
| Rate Limit Respect | ✅ PASS / ❌ FAIL | X min | |

**Overall:** X/Y tests passed (Z%)

---

## Detailed Results

### Full Payment Cycle
- **Invoice Detection:** ✅ PASS / ❌ FAIL
- **PDF Parsing:** ✅ PASS / ❌ FAIL (confidence: X.XX)
- **State Creation:** ✅ PASS / ❌ FAIL
- **Reminder Scheduling:** ✅ PASS / ❌ FAIL
- **Payment Detection:** ✅ PASS / ❌ FAIL (latency: X.Xs)
- **State Update:** ✅ PASS / ❌ FAIL
- **Archive:** ✅ PASS / ❌ FAIL
- **Supervisor Validation:** ✅ PASS / ❌ FAIL

### Error Handling Tests

#### OAuth Failure
- **Detection:** ✅ PASS / ❌ FAIL
- **Graceful Degradation:** ✅ PASS / ❌ FAIL
- **Recovery:** ✅ PASS / ❌ FAIL

#### PDF Parse Failure
- **Detection:** ✅ PASS / ❌ FAIL
- **Manual Queue:** ✅ PASS / ❌ FAIL
- **No Crash:** ✅ PASS / ❌ FAIL

#### Permission Denied
- **Detection:** ✅ PASS / ❌ FAIL
- **Escalation:** ✅ PASS / ❌ FAIL
- **System Stable:** ✅ PASS / ❌ FAIL

### Recovery Tests

#### Crash Recovery
- **Detection:** ✅ PASS / ❌ FAIL
- **Auto-Restart:** ✅ PASS / ❌ FAIL
- **State Preserved:** ✅ PASS / ❌ FAIL

#### Rate Limit Respect
- **Limit Enforcement:** ✅ PASS / ❌ FAIL
- **Proper Queuing:** ✅ PASS / ❌ FAIL
- **No 429 Errors:** ✅ PASS / ❌ FAIL

---

## Performance Metrics

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Payment Detection Latency | X.Xs | <30s | ✅/❌ |
| Email Send Latency | X.Xs | <5s | ✅/❌ |
| State Update Latency | X.Xs | <1s | ✅/❌ |
| Supervisor Check Duration | X.Xs | <10s | ✅/❌ |

---

## Issues Found

### Critical Issues (Must Fix)
1. [Issue description]
2. [Issue description]

### Major Issues (Should Fix)
1. [Issue description]
2. [Issue description]

### Minor Issues (Nice to Have)
1. [Issue description]
2. [Issue description]

---

## Recommendations

**Overall Assessment:** PRODUCTION READY / NOT READY

**Required Actions:**
1. Fix critical issues
2. Re-run E2E tests
3. Obtain sign-off from stakeholders

---

## Test Evidence

- **Test Scripts:** `novotechno-collections/scripts/run_e2e_tests.py`
- **Test Logs:** [location]
- **Screenshots:** [location]
- **Duration:** [time]

---

## Sign-Off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| QA Engineer | | | |
| Project Lead | | | |
| Operations | | | |
```

## Dependencies
- TASK_CLI_001, TASK_CLI_002, TASK_CLI_003 (all must complete first)
- pytest for test execution

## Output Files
- `novotechno-collections/tests/test_e2e.py` (150 lines)
- `novotechno-collections/scripts/run_e2e_tests.py` (100 lines)
- `~/.openclaw/workspace-qa-engineer-novotechno/E2E-TEST-RESULTS.md` (test report)

## Definition of Done
- [ ] All 6 E2E scenarios tested
- [ ] Full payment cycle passes
- [ ] Error handling validated
- [ ] Performance metrics within targets
- [ ] Test report written
- [ ] RESPONSE file written

## Success Criteria
- [ ] E2E cycle completes without manual intervention
- [ ] All error scenarios handled gracefully
- [ ] State consistency maintained
- [ ] **GATE:** Production readiness sign-off

## Previous Task
TASK_CLI_001, TASK_CLI_002, TASK_CLI_003 (all must complete first)

## Next Task
TASK_DOCS_001 (documentation) — can run in parallel
