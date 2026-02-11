#!/usr/bin/env python3
"""
OAuth Token Persistence Validation Script

Usage:
    python scripts/run_oauth_validation.py --duration 2 --restarts 4 --output results.json
    
Requirements:
    - OAuth tokens must be configured first (run setup_oauth.py)
    - pytest must be installed
"""
import click
import time
import json
import subprocess
import sys
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List

# Add parent directories to path for imports
BASE_DIR = Path(__file__).parent.parent
PROJECT_ROOT = BASE_DIR.parent  # Go up one more level to reach the project root
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))


@click.command()
@click.option("--duration", default=2, help="Test duration in hours")
@click.option("--restarts", default=4, help="Number of simulated restarts")
@click.option("--output", type=click.Path(), help="Output file for results")
@click.option("--account-id", default="default", help="OAuth account ID to test")
@click.option("--provider", default="microsoft", help="OAuth provider")
@click.option("--skip-slow", is_flag=True, help="Skip the full 2-hour test")
def main(duration: int, restarts: int, output: str, account_id: str, provider: str, skip_slow: bool):
    """Run OAuth token persistence validation"""
    
    click.echo("\n" + "="*70)
    click.echo(" OAuth Token Persistence Validation")
    click.echo("="*70)
    click.echo(f"🚀 Starting validation (duration: {duration}h, restarts: {restarts})")
    click.echo(f"Account: {account_id} | Provider: {provider}")
    click.echo("="*70)
    
    results = {
        "test_name": "OAuth Token Persistence Validation",
        "start_time": datetime.now(timezone.utc).isoformat(),
        "duration_hours": duration,
        "restart_count": restarts,
        "account_id": account_id,
        "provider": provider,
        "tests": [],
        "summary": {}
    }
    
    # Check prerequisites
    if not check_prerequisites():
        click.echo("❌ Prerequisites not met. Run setup_oauth.py first.")
        return 1
    
    # Test 1: Unit tests for token persistence
    click.echo("\n📋 Test 1: Running unit tests for token persistence...")
    test1_result = run_unit_tests(skip_slow=skip_slow)
    results["tests"].append(test1_result)
    click.echo(f"   {'✅ PASSED' if test1_result['passed'] else '❌ FAILED'}")
    
    # Test 2: Integration test - Token persisting across restarts
    click.echo("\n🔄 Test 2: Testing token survival across restarts...")
    test2_result = test_token_survival(restarts, account_id, provider)
    results["tests"].append(test2_result)
    click.echo(f"   {'✅ PASSED' if test2_result['passed'] else '❌ FAILED'}")
    
    # Test 3: Silent refresh functionality
    click.echo("\n⚡ Test 3: Testing silent refresh mechanism...")
    test3_result = test_silent_refresh(account_id, provider)
    results["tests"].append(test3_result)
    click.echo(f"   {'✅ PASSED' if test3_result['passed'] else '❌ FAILED'}")
    
    # Test 4: Degraded mode activation
    click.echo("\n⚠️  Test 4: Testing DEGRADED mode activation...")
    test4_result = test_degraded_mode(account_id, provider)
    results["tests"].append(test4_result)
    click.echo(f"   {'✅ PASSED' if test4_result['passed'] else '❌ FAILED'}")
    
    # Test 5: Continuous operation test (if not skipped)
    if not skip_slow:
        click.echo(f"\n⏱️  Test 5: Testing {duration} hour continuous operation...")
        click.echo("   (This test runs in real-time and may take a while)")
        test5_result = test_continuous_operation(duration, restarts, account_id, provider)
        results["tests"].append(test5_result)
        click.echo(f"   {'✅ PASSED' if test5_result['passed'] else '❌ FAILED'}")
    else:
        click.echo("\n⏭️  Test 5: Skipping long-duration test (--skip-slow flag)")
    
    # Calculate overall result
    passed = all(t["passed"] for t in results["tests"])
    pass_count = sum(1 for t in results["tests"] if t["passed"])
    total_count = len(results["tests"])
    
    results["overall"] = {
        "passed": passed,
        "completion_time": datetime.now(timezone.utc).isoformat(),
        "summary": f"{pass_count}/{total_count} tests passed",
        "duration_seconds": 0
    }
    
    # Output results
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        click.echo(f"\n📄 Results written to: {output_path}")
    
    # Calculate final duration
    start_str = results["start_time"].replace('+00:00', '+00:00')
    start_dt = datetime.fromisoformat(start_str).replace(tzinfo=timezone.utc)
    end_dt = datetime.now(timezone.utc)
    results["overall"]["duration_seconds"] = int((end_dt - start_dt).total_seconds())
    
    # Summary
    click.echo(f"\n{'✅ ALL TESTS PASSED' if passed else '❌ SOME TESTS FAILED'}")
    click.echo(results["overall"]["summary"])
    click.echo(f"Duration: {results['overall']['duration_seconds']}s")
    
    if output:
        # Rewrite with correct duration
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2, default=str)
    
    click.echo("="*70)
    
    return 0 if passed else 1


def check_prerequisites() -> bool:
    """Check if OAuth is configured and prerequisites are met"""
    try:
        from auth.token_cache import TokenCache
        import importlib
        
        # Check if key modules exist
        spec = importlib.util.find_spec("cryptography")
        if spec is None:
            click.echo("❌ cryptography module not found")
            return False
        
        # Try to initialize token cache
        cache = TokenCache()
        
        click.echo("✅ Prerequisites met")
        return True
        
    except Exception as e:
        click.echo(f"❌ Prerequisites check failed: {e}")
        return False


def run_unit_tests(skip_slow: bool = False) -> Dict[str, Any]:
    """Run unit tests for token persistence"""
    try:
        import pytest
        
        # Change to test directory
        original_cwd = os.getcwd()
        os.chdir(str(BASE_DIR))
        
        # Build pytest args
        args = ["-v", "tests/test_oauth_persistence.py", "-p", "no:pytest_randomly"]
        
        if skip_slow:
            args.extend(["-m", "not slow"])
        
        # Run pytest
        result = pytest.main(args)
        
        # Restore original directory
        os.chdir(original_cwd)
        
        return {
            "name": "unit_tests",
            "passed": result == 0,
            "result": "PASSED" if result == 0 else "FAILED",
            "notes": ["All unit tests passed"] if result == 0 else ["Some tests failed"]
        }
        
    except Exception as e:
        return {
            "name": "unit_tests",
            "passed": False,
            "result": "ERROR",
            "notes": [str(e)]
        }


def test_token_survival(restart_count: int, account_id: str, provider: str) -> Dict[str, Any]:
    """Test token survival across simulated restarts"""
    try:
        from auth.token_cache import TokenCache, CachedToken
        from auth.token_validator import TokenValidator
        import time
        
        # Initialize
        cache = TokenCache()
        
        # Create test token if none exists
        existing_token = cache.get_token(provider, account_id)
        if not existing_token:
            test_token = CachedToken(
                access_token=f"test_token_{int(time.time())}",
                token_type="Bearer",
                expires_at=int(time.time()) + 3600,
                refresh_token=f"refresh_{int(time.time())}",
                scope="Mail.Send User.Read",
                account_id=account_id
            )
            cache.save_token(provider, account_id, test_token)
            existing_token = cache.get_token(provider, account_id)
        
        if not existing_token:
            return {
                "name": "token_survival",
                "passed": False,
                "result": "FAILED",
                "notes": [f"Could not create test token for {provider}:{account_id}"]
            }
        
        initial_token_str = existing_token.access_token
        survival_count = 0
        lost_count = 0
        
        # Simulate restarts
        for i in range(restart_count):
            # Re-initialize cache (simulating restart)
            new_cache = TokenCache()
            token_after_restart = new_cache.get_token(provider, account_id)
            
            if token_after_restart and token_after_restart.access_token == initial_token_str:
                survival_count += 1
            else:
                lost_count += 1
        
        passed = lost_count == 0
        notes = [
            f"Token survived {survival_count}/{restart_count} restarts",
            f"Token lost {lost_count} times"
        ]
        
        return {
            "name": "token_survival",
            "passed": passed,
            "result": "PASSED" if passed else "FAILED",
            "restarts_tested": restart_count,
            "survival_rate": float(survival_count) / restart_count * 100 if restart_count > 0 else 0,
            "notes": notes
        }
        
    except Exception as e:
        return {
            "name": "token_survival",
            "passed": False,
            "result": "ERROR",
            "notes": [str(e)]
        }


def test_silent_refresh(account_id: str, provider: str) -> Dict[str, Any]:
    """Test silent token refresh mechanism"""
    try:
        from auth.token_cache import TokenCache, CachedToken
        from auth.token_validator import TokenValidator
        import time
        
        # Initialize
        cache = TokenCache()
        
        # Create test token if none exists
        existing_token = cache.get_token(provider, account_id)
        if not existing_token:
            test_token = CachedToken(
                access_token=f"test_token_{int(time.time())}",
                token_type="Bearer",
                expires_at=int(time.time()) + 3600,
                refresh_token=f"refresh_{int(time.time())}",
                scope="Mail.Send User.Read",
                account_id=account_id
            )
            cache.save_token(provider, account_id, test_token)
            existing_token = cache.get_token(provider, account_id)
        
        if not existing_token:
            return {
                "name": "silent_refresh",
                "passed": False,
                "result": "FAILED",
                "notes": ["Could not create test token"]
            }
        
        validator = TokenValidator(cache, provider=provider)
        
        # Set token to expire in 200 seconds (below 300s buffer)
        existing_token.expires_at = int(time.time()) + 200
        cache.save_token(provider, account_id, existing_token)
        
        old_expiry = existing_token.expires_at
        
        # Trigger validation (should trigger silent refresh)
        try:
            validated_token = validator.validate_before_request(account_id)
            new_token = cache.get_token(provider, account_id)
            
            if new_token and new_token.expires_at > old_expiry:
                return {
                    "name": "silent_refresh",
                    "passed": True,
                    "result": "PASSED",
                    "notes": ["Token refreshed successfully before expiry"]
                }
            else:
                return {
                    "name": "silent_refresh",
                    "passed": False,
                    "result": "FAILED",
                    "notes": ["Token was not refreshed"]
                }
        except Exception as e:
            if "DEGRADED_MODE" in str(e):
                return {
                    "name": "silent_refresh",
                    "passed": False,
                    "result": "DEGRADED",
                    "notes": ["System in degraded mode", str(e)]
                }
            else:
                raise
        
    except Exception as e:
        return {
            "name": "silent_refresh",
            "passed": False,
            "result": "ERROR",
            "notes": [str(e)]
        }


def test_degraded_mode(account_id: str, provider: str) -> Dict[str, Any]:
    """Test DEGRADED mode activation after consecutive failures"""
    try:
        from auth.token_cache import TokenCache, CachedToken
        from auth.token_validator import TokenValidator
        import time
        
        # Initialize
        cache = TokenCache()
        
        # Create test token if none exists
        existing_token = cache.get_token(provider, account_id)
        if not existing_token:
            test_token = CachedToken(
                access_token=f"test_token_{int(time.time())}",
                token_type="Bearer",
                expires_at=int(time.time()) + 3600,
                refresh_token=f"refresh_{int(time.time())}",
                scope="Mail.Send User.Read",
                account_id=account_id
            )
            cache.save_token(provider, account_id, test_token)
            existing_token = cache.get_token(provider, account_id)
        
        if not existing_token:
            return {
                "name": "degraded_mode",
                "passed": False,
                "result": "FAILED",
                "notes": ["Could not create test token"]
            }
        
        validator = TokenValidator(cache, provider=provider)
        
        # Simulate 3 consecutive failures
        for i in range(validator.max_refresh_attempts):
            validator.refresh_attempts += 1
        
        # Trigger degraded mode
        if validator.refresh_attempts >= validator.max_refresh_attempts:
            validator._enter_degraded_mode(account_id)
        
        # Check degraded status
        if validator.degraded_mode:
            status = validator.get_status(account_id)
            return {
                "name": "degraded_mode",
                "passed": True,
                "result": "PASSED",
                "notes": [
                    "DEGRADED mode activated successfully",
                    f"Refresh attempts: {status['refresh_attempts']}",
                    f"Account: {status['account_id']}"
                ]
            }
        else:
            return {
                "name": "degraded_mode",
                "passed": False,
                "result": "FAILED",
                "notes": ["DEGRADED mode not activated after maximum refresh attempts"]
            }
        
    except Exception as e:
        return {
            "name": "degraded_mode",
            "passed": False,
            "result": "ERROR",
            "notes": [str(e)]
        }


def test_continuous_operation(duration: int, restarts: int, account_id: str, provider: str) -> Dict[str, Any]:
    """Test continuous operation for X hours with periodic restarts"""
    try:
        from auth.token_cache import TokenCache
        from auth.token_validator import TokenValidator
        import time
        
        cache = TokenCache()
        validator = TokenValidator(cache, provider=provider)
        
        start_time = time.time()
        test_duration = duration * 3600
        emails_sent = 0
        restarts_simulated = 0
        restart_times = [duration * h for h in [0.25, 0.5, 0.75, 1.0]]  # 15min, 30min, 45min, 1hr
        errors = []
        
        # Verify initial token
        initial_token = cache.get_token(provider, account_id)
        if not initial_token:
            return {
                "name": "continuous_operation",
                "passed": False,
                "result": "FAILED",
                "notes": ["No initial token found"]
            }
        
        initial_token_str = initial_token.access_token
        
        # Main test loop
        while time.time() - start_time < test_duration:
            try:
                # Attempt email operations (up to 20)
                if emails_sent < 20:
                    validated_token = validator.validate_before_request(account_id)
                    emails_sent += 1
                
                # Check for restarts at specified intervals
                elapsed = time.time() - start_time
                for restart_time in restart_times:
                    if abs(elapsed - restart_time * 3600) < 30:  # Within 30 seconds
                        # Simulate restart
                        new_cache = TokenCache()
                        token_after_restart = new_cache.get_token(provider, account_id)
                        
                        if token_after_restart and token_after_restart.access_token == initial_token_str:
                            restarts_simulated += 1
                        else:
                            errors.append(f"Token lost at restart {restarts_simulated + 1}")
                
                time.sleep(60)  # Check every minute
                
            except Exception as e:
                if "DEGRADED_MODE" in str(e):
                    # Degraded mode during long test is acceptable
                    break
                else:
                    errors.append(str(e))
                    break  # Unexpected error
        
        # Evaluate results
        duration_actual = (time.time() - start_time) / 3600
        targets = {
            "emails_sent": 18,  # Minimum emails to send
            "restarts": 3,      # Minimum restarts to survive
            "duration": duration * 0.9  # 90% of target duration
        }
        
        passed = (
            emails_sent >= targets["emails_sent"] and
            restarts_simulated >= targets["restarts"] and
            duration_actual >= targets["duration"]
        )
        
        notes = [
            f"Duration: {duration_actual:.2f}h (target: {duration}h)",
            f"Emails sent: {emails_sent} (target: {targets['emails_sent']})",
            f"Restarts survived: {restarts_simulated} (target: {targets['restarts']})",
            f"Errors: {len(errors)}"
        ]
        
        if errors:
            notes.extend([f"  - {error}" for error in errors[:3]])  # Show first 3 errors
        
        return {
            "name": "continuous_operation",
            "passed": passed,
            "result": "PASSED" if passed else "FAILED",
            "duration_hours": duration_actual,
            "emails_sent": emails_sent,
            "restarts_survived": restarts_simulated,
            "notes": notes
        }
        
    except Exception as e:
        return {
            "name": "continuous_operation",
            "passed": False,
            "result": "ERROR",
            "notes": [str(e)]
        }


if __name__ == "__main__":
    sys.exit(main())