#!/usr/bin/env python3
"""
End-to-End Test Runner

Usage:
    python scripts/run_e2e_tests.py --output results.json
"""

import click
import json
import time
import sys
from datetime import datetime
from pathlib import Path
import subprocess
import tempfile
import shutil

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def run_pytest_scenario(test_name, verbose=False):
    """Run a single pytest scenario."""
    try:
        cmd = [
            "python3", "-m", "pytest", 
            "tests/test_e2e.py::TestFullPaymentCycle::" + test_name,
            "-v", "--tb=short"
        ]
        
        if verbose:
            click.echo(f"  Running: {' '.join(cmd)}")
        
        start_time = time.time()
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )
        elapsed = time.time() - start_time
        
        passed = result.returncode == 0
        
        if verbose and not passed:
            click.echo(f"  Output: {result.stdout}")
            click.echo(f"  Error: {result.stderr}")
        
        return {
            "passed": passed,
            "duration": elapsed,
            "exit_code": result.returncode,
            "stdout": result.stdout if not passed else "",
            "stderr": result.stderr if not passed else ""
        }
        
    except Exception as e:
        return {
            "passed": False,
            "duration": 0,
            "error": str(e)
        }


@click.command()
@click.option("--output", type=click.Path(), help="Output file for results")
@click.option("--verbose", is_flag=True, help="Verbose output")
@click.option("--quick", is_flag=True, help="Skip slow tests")
def main(output: str, verbose: bool, quick: bool):
    """Run end-to-end integration tests"""
    
    results = {
        "test_name": "E2E Integration Testing",
        "start_time": datetime.utcnow().isoformat(),
        "scenarios": [],
        "env": {
            "python": sys.version,
            "cwd": str(Path.cwd())
        }
    }
    
    click.echo("🚀 Starting E2E Integration Tests\n")
    
    # Test scenarios mapping
    scenarios = [
        ("Full Payment Cycle", "test_full_cycle_invoice_to_archive"),
        ("OAuth Failure Handling", "test_error_handling_oauth_failure"),
        ("PDF Parse Failure", "test_error_handling_pdf_parse_failure"),
        ("Permission Denied", "test_permission_denied_handling"),
        ("Crash Recovery", "test_supervisor_recovery_after_crash"),
        ("Rate Limit Respect", "test_rate_limit_respect"),
    ]
    
    if quick:
        scenarios = scenarios[:3]  # Only run first 3 tests in quick mode
        click.echo("⚡ Quick mode: Running only core tests\n")
    
    passed = 0
    failed = 0
    total_duration = 0
    
    for scenario_name, test_func in scenarios:
        click.echo(f"📋 {scenario_name}...")
        
        try:
            result = run_pytest_scenario(test_func, verbose)
            
            if result["passed"]:
                click.echo(f"  ✅ PASSED ({result['duration']:.1f}s)")
                passed += 1
            else:
                error_msg = result.get('error', result.get('stderr', 'Unknown error'))[:100]
                click.echo(f"  ❌ FAILED: {error_msg}")
                failed += 1
            
            total_duration += result.get("duration", 0)
            
            results["scenarios"].append({
                "name": scenario_name,
                "passed": result["passed"],
                "duration_seconds": result.get("duration", 0),
                "exit_code": result.get("exit_code", -1),
                "error": result.get("error") or result.get("stderr", "")[:200]
            })
            
        except Exception as e:
            click.echo(f"  ❌ ERROR: {e}")
            failed += 1
            results["scenarios"].append({
                "name": scenario_name,
                "passed": False,
                "duration_seconds": 0,
                "error": str(e)
            })
        
        # Small delay between tests
        time.sleep(0.5)
    
    # Performance tests
    performance_tests = [
        ("Payment Detection Latency", "test_payment_detection_latency"),
        ("State Update Latency", "test_state_update_latency"),
        ("Supervisor Check Duration", "test_supervisor_check_duration"),
    ]
    
    if not quick:
        click.echo("\n⚡ Performance Tests:")
        performance_passed = 0
        
        for scenario_name, test_func in performance_tests:
            click.echo(f"📋 {scenario_name}...")
            
            result = run_pytest_scenario(test_func, verbose)
            
            if result["passed"]:
                click.echo(f"  ✅ PASSED ({result['duration']:.1f}s)")
                performance_passed += 1
            else:
                error_msg = result.get('error', result.get('stderr', 'Unknown error'))[:80]
                click.echo(f"  ❌ FAILED: {error_msg}")
            
            total_duration += result.get("duration", 0)
            results["scenarios"].append({
                "name": scenario_name,
                "passed": result["passed"],
                "duration_seconds": result.get("duration", 0),
                "type": "performance"
            })
        
        passed += performance_passed
    
    # Summary
    results["summary"] = {
        "total": len(scenarios) if quick else len(scenarios) + len(performance_tests),
        "passed": passed,
        "failed": failed,
        "completion_time": datetime.utcnow().isoformat(),
        "total_duration_seconds": total_duration,
        "success_rate": f"{passed}/{len(scenarios) if quick else len(scenarios) + len(performance_tests)} ({passed/(len(scenarios) if quick else len(scenarios) + len(performance_tests))*100:.1f}%)"
    }
    
    # Final status
    if failed == 0 and passed > 0:
        status_emoji = "✅"
        status_text = "ALL TESTS PASSED"
        exit_code = 0
    elif failed > 0:
        status_emoji = "❌"
        status_text = f"{failed} TEST(S) FAILED"
        exit_code = 1
    else:
        status_emoji = "⚠️"
        status_text = "NO TESTS RUN"
        exit_code = 2
    
    click.echo(f"\n{status_emoji} {status_text}")
    click.echo(f"Success Rate: {results['summary']['success_rate']}")
    click.echo(f"Duration: {total_duration:.1f}s")
    
    # Output results to JSON
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)
        click.echo(f"\n📄 Results: {output}")
    
    # Also save to workspace
    workspace_results = Path.cwd() / "e2e_results.json"
    with open(workspace_results, 'w') as f:
        json.dump(results, f, indent=2)
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
