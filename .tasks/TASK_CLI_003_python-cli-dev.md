# TASK: collections-supervisor CLI
**Task ID:** TASK_CLI_003
**Owner:** python-cli-dev-novotechno
**Type:** implementation
**Priority:** P1
**Status:** PENDING
**Created:** 2026-02-11 08:00 GMT-5

## Context
Implement the collections-supervisor CLI that monitors agent health, coordinates payments, and provides dashboard/reporting.

## Requirements

### 1. Health Checker
**File:** `novotechno-collections/src/supervisor/health_checker.py`

**Implementation:**
```python
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path

class AgentHealthStatus:
    """Track agent health status"""
    
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.last_heartbeat = None
        self.status = "unknown"
        self.restarts = 0
        self.errors = []
    
    def update_heartbeat(self):
        """Record heartbeat"""
        self.last_heartbeat = datetime.utcnow()
        self.status = "healthy"
        self.errors = []
    
    def mark_unhealthy(self, reason: str):
        """Mark agent as unhealthy"""
        self.status = "unhealthy"
        self.errors.append({
            "timestamp": datetime.utcnow().isoformat(),
            "reason": reason
        })
    
    def is_stale(self, max_age_minutes: int = 60) -> bool:
        """Check if heartbeat is stale"""
        if not self.last_heartbeat:
            return True
        age = datetime.utcnow() - self.last_heartbeat
        return age > timedelta(minutes=max_age_minutes)

class HealthChecker:
    """Monitor agent health"""
    
    HEARTBEAT_TIMEOUT_MINUTES = 60
    MISSED_THRESHOLD = 2  # Missed 2 heartbeats = escalation
    
    def __init__(self, agents: List[str]):
        self.agents = {name: AgentHealthStatus(name) for name in agents}
        self.logger = logging.getLogger(__name__)
    
    def check_all(self) -> Dict:
        """Run health check on all agents"""
        results = {}
        
        for name, status in self.agents.items():
            result = self._check_agent(name, status)
            results[name] = result
        
        return results
    
    def _check_agent(self, name: str, status: AgentHealthStatus) -> Dict:
        """Check individual agent health"""
        if status.is_stale(self.HEARTBEAT_TIMEOUT_MINUTES):
            status.mark_unhealthy("No heartbeat received")
            
            # Check if should escalate
            missed_count = self._count_missed_heartbeats(name)
            
            if missed_count >= self.MISSED_THRESHOLD:
                self._escalate_agent_failure(name, missed_count)
                status.status = "escalated"
            else:
                self._try_auto_restart(name)
                status.status = "restarting"
        
        return {
            "name": name,
            "status": status.status,
            "last_heartbeat": status.last_heartbeat.isoformat() if status.last_heartbeat else None,
            "errors": status.errors[-5:],  # Last 5 errors
            "restarts": status.restarts
        }
    
    def _count_missed_heartbeats(self, agent_name: str) -> int:
        """Count consecutive missed heartbeats"""
        # Read from heartbeat log
        log_file = Path.home() / ".cache" / "novotechno-collections" / "heartbeats" / f"{agent_name}.log"
        if not log_file.exists():
            return self.MISSED_THRESHOLD
        
        with open(log_file) as f:
            lines = f.readlines()
        
        # Count consecutive stale entries
        stale_count = 0
        for line in reversed(lines[-10:]):  # Check last 10 entries
            entry = json.loads(line)
            if entry.get("stale"):
                stale_count += 1
            else:
                break
        
        return stale_count
    
    def _escalate_agent_failure(self, agent_name: str, missed_count: int):
        """Escalate agent failure to human"""
        self.logger.critical(f"🚨 ESCALATION: {agent_name} failed {missed_count}x")
        
        message = {
            "type": "AGENT_ESCALATION",
            "agent": agent_name,
            "missed_heartbeats": missed_count,
            "timestamp": datetime.utcnow().isoformat(),
            "action_required": "Manual intervention required"
        }
        
        # Notify Caine
        self._notify_caine(message)
    
    def _try_auto_restart(self, agent_name: str):
        """Attempt automatic restart"""
        try:
            # Would execute: openclaw agent --agent {agent_name} --message "restart"
            self.logger.info(f"🔄 Auto-restarting {agent_name}")
            # Subprocess call here
        except Exception as e:
            self.logger.error(f"❌ Auto-restart failed: {e}")
    
    def _notify_caine(self, message: Dict):
        """Send notification to Caine"""
        # Would use sessions_send
        # For now, log it
        self.logger.critical(f"📢 WOULD NOTIFY CAINE: {message}")

class StateConsistencyChecker:
    """Verify state consistency across agents"""
    
    def __init__(self, state_dir: str):
        self.state_dir = Path(state_dir)
        self.logger = logging.getLogger(__name__)
    
    def reconcile_all(self) -> Dict:
        """Reconcile all state files"""
        results = {
            "invoices": self._reconcile_invoices(),
            "ledger": self._reconcile_ledger(),
            "queue": self._check_queue_health(),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return results
    
    def _reconcile_invoices(self) -> Dict:
        """Verify invoice state consistency"""
        unpaid_total = 0
        paid_total = 0
        errors = []
        
        for state_file in self.state_dir.rglob("*.json"):
            if "archive" in str(state_file):
                continue
            
            try:
                with open(state_file) as f:
                    data = json.load(f)
                
                amount = data.get("amount", 0)
                status = data.get("status", "unknown")
                
                if status == "unpaid":
                    unpaid_total += amount
                elif status == "paid":
                    paid_total += amount
                    
            except Exception as e:
                errors.append({"file": str(state_file), "error": str(e)})
        
        return {
            "unpaid_total": unpaid_total,
            "paid_total": paid_total,
            "error_count": len(errors),
            "errors": errors[:10]  # First 10 errors
        }
    
    def _reconcile_ledger(self) -> Dict:
        """Verify ledger totals match state"""
        # Read ledger totals
        ledger_total = self._read_ledger_totals()
        
        # Read state totals
        state = self._reconcile_invoices()
        
        discrepancies = []
        if abs(ledger_total["unpaid"] - state["unpaid_total"]) > 0.01:
            discrepancies.append({
                "type": "unpaid_mismatch",
                "ledger": ledger_total["unpaid"],
                "state": state["unpaid_total"]
            })
        
        return {
            "ledger": ledger_total,
            "state": state,
            "discrepancies": discrepancies,
            "consistent": len(discrepancies) == 0
        }
    
    def _read_ledger_totals(self) -> Dict:
        """Read totals from ledger"""
        # Would parse QMD ledger
        # For now, return mock
        return {"unpaid": 0, "paid": 0, "escalated": 0}
    
    def _check_queue_health(self) -> Dict:
        """Check queue health"""
        queue_dir = Path.home() / ".cache" / "novotechno-collections" / "queues"
        
        if not queue_dir.exists():
            return {"healthy": True, "queues": []}
        
        queues = {}
        for queue_file in queue_dir.glob("*.jsonl"):
            with open(queue_file) as f:
                lines = f.readlines()
            queues[queue_file.stem] = len(lines)
        
        return {
            "healthy": all(count < 100 for count in queues.values()),
            "queues": queues
        }
```

### 2. Dashboard Generator
**File:** `novotechno-collections/src/supervisor/dashboard.py`

**Implementation:**
```python
from datetime import datetime, timedelta
from typing import Dict, List
import json

class Dashboard:
    """Generate HTML dashboard"""
    
    def __init__(self, state_dir: str, health_checker, config: Dict):
        self.state_dir = state_dir
        self.health = health_checker
        self.config = config
    
    def generate(self) -> str:
        """Generate HTML dashboard"""
        health_status = self.health.check_all()
        state_summary = self._get_state_summary()
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>NovotEcho Collections Dashboard</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .status-healthy {{ color: green; }}
        .status-unhealthy {{ color: red; }}
        .status-unknown {{ color: orange; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #4CAF50; color: white; }}
        .metric {{ font-size: 24px; }}
    </style>
</head>
<body>
    <h1>📊 NovotEcho Collections Dashboard</h1>
    <p>Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</p>
    
    <h2>💚 Agent Health</h2>
    {self._render_agent_table(health_status)}
    
    <h2>💰 Collection Status</h2>
    {self._render_state_summary(state_summary)}
    
    <h2>⚡ Quick Actions</h2>
    <button onclick="location.reload()">🔄 Refresh</button>
    <button onclick="alert('Would trigger health check')">🏥 Run Health Check</button>
</body>
</html>"""
        return html
    
    def _render_agent_table(self, health_status: Dict) -> str:
        """Render agent health table"""
        rows = []
        for name, status in health_status.items():
            status_class = f"status-{status['status']}"
            rows.append(f"""
            <tr>
                <td>{name}</td>
                <td class="{status_class}">{status['status']}</td>
                <td>{status.get('last_heartbeat', 'N/A')}</td>
                <td>{status.get('restarts', 0)}</td>
            </tr>
            """)
        
        return f"""
        <table>
            <tr><th>Agent</th><th>Status</th><th>Last Heartbeat</th><th>Restarts</th></tr>
            {''.join(rows)}
        </table>
        """
    
    def _render_state_summary(self, summary: Dict) -> str:
        """Render state summary"""
        return f"""
        <table>
            <tr><th>Status</th><th>Count</th><th>Total Amount</th></tr>
            <tr><td>Unpaid</td><td class="metric">{summary['unpaid_count']}</td><td class="metric">${summary['unpaid_total']:,.2f}</td></tr>
            <tr><td>Paid</td><td class="metric">{summary['paid_count']}</td><td class="metric">${summary['paid_total']:,.2f}</td></tr>
            <tr><td>Escalated</td><td class="metric">{summary['escalated_count']}</td><td class="metric">${summary['escalated_total']:,.2f}</td></tr>
            <tr><td>In Review</td><td class="metric">{summary['review_count']}</td><td>-</td></tr>
        </table>
        """
    
    def _get_state_summary(self) -> Dict:
        """Get state summary metrics"""
        # Would read from state files
        return {
            "unpaid_count": 0,
            "unpaid_total": 0,
            "paid_count": 0,
            "paid_total": 0,
            "escalated_count": 0,
            "escalated_total": 0,
            "review_count": 0
        }

class MetricsCollector:
    """Collect metrics for reporting"""
    
    def __init__(self, state_dir: str):
        self.state_dir = state_dir
    
    def get_metrics(self, hours: int = 24) -> Dict:
        """Get metrics for time window"""
        since = datetime.utcnow() - timedelta(hours=hours)
        
        return {
            "emails_sent": self._count_emails(since),
            "payments_detected": self._count_payments(since),
            "errors": self._count_errors(since),
            "avg_latency": self._avg_payment_latency(since)
        }
    
    def _count_emails(self, since: datetime) -> int:
        """Count emails sent"""
        return 0  # Would query logs
    
    def _count_payments(self, since: datetime) -> int:
        """Count payments detected"""
        return 0
    
    def _count_errors(self, since: datetime) -> int:
        """Count errors"""
        return 0
    
    def _avg_payment_latency(self, since: datetime) -> float:
        """Average payment detection latency"""
        return 0.0
```

### 3. CLI Entry Point
**File:** `novotechno-collections/scripts/collections-supervisor.py`

```python
#!/usr/bin/env python3
import click
import signal
import sys
import json
from src.supervisor.health_checker import HealthChecker, StateConsistencyChecker
from src.supervisor.dashboard import Dashboard, MetricsCollector

@click.command()
@click.option("--health-check", is_flag=True, help="Run health check only")
@click.option("--dashboard", is_flag=True, help="Generate dashboard")
@click.option("--output", type=click.Path(), help="Output file for dashboard")
@click.option("--agents", default="collections-emailer,payment-watcher", help="Comma-separated agent list")
def main(health_check: bool, dashboard: bool, output: str, agents: str):
    """Collections Supervisor - Agent health and coordination"""
    
    agent_list = agents.split(",")
    
    # Initialize components
    health_checker = HealthChecker(agent_list)
    consistency_checker = StateConsistencyChecker()
    metrics = MetricsCollector()
    dashboard_gen = Dashboard(consistency_checker.state_dir, health_checker, {})
    
    def shutdown_handler(signum, frame):
        click.echo("\n🛑 Supervisor shutting down...")
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)
    
    try:
        if health_check:
            # Run health check
            results = health_checker.check_all()
            click.echo("\n💚 Agent Health Status:")
            for name, status in results.items():
                status_emoji = "✅" if status["status"] == "healthy" else "❌"
                click.echo(f"{status_emoji} {name}: {status['status']}")
            
            # State consistency
            consistency = consistency_checker.reconcile_all()
            click.echo(f"\n🔍 State Consistency: {'✅ OK' if consistency['ledger']['consistent'] else '❌ MISMATCH'}")
            
        elif dashboard:
            # Generate dashboard
            html = dashboard_gen.generate()
            
            if output:
                with open(output, 'w') as f:
                    f.write(html)
                click.echo(f"📊 Dashboard written to: {output}")
            else:
                click.echo(html)
        
        else:
            # Full supervisor mode
            click.echo("🚀 Collections Supervisor started")
            click.echo(f"👀 Monitoring: {', '.join(agent_list)}")
            
            # Run periodic health checks
            while True:
                results = health_checker.check_all()
                
                # Log results
                for name, status in results.items():
                    if status['status'] != 'healthy':
                        click.echo(f"⚠️ {name}: {status['status']}")
                
                # Hourly dashboard update
                dashboard_gen.generate()
                
                # Sleep 15 minutes
                import time
                time.sleep(900)
    
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
```

## Dependencies
- Standard library only (json, pathlib, datetime)

## Output Files
- `novotechno-collections/src/supervisor/__init__.py`
- `novotechno-collections/src/supervisor/health_checker.py` (200 lines)
- `novotechno-collections/src/supervisor/dashboard.py` (150 lines)
- `novotechno-collections/scripts/collections-supervisor.py` (100 lines)
- `novotechno-collections/tests/test_health_checker.py` (80 lines)

## Definition of Done
- [ ] Health checker functional
- [ ] Dashboard generates correctly
- [ ] Escalation triggers correctly
- [ ] All tests pass
- [ ] RESPONSE file written

## Success Criteria
- [ ] Health check detects missed heartbeats
- [ ] Escalation triggers after 2 missed checks
- [ ] Dashboard shows accurate metrics
- [ ] State consistency validation works

## Dependencies
- TASK_CLI_001 (collections-emailer) - must complete first
- TASK_CLI_002 (payment-watcher) - must complete first

## Next Tasks
- TASK_QA_001, TASK_QA_002, TASK_QA_003 (validation)
- TASK_DOCS_001 (documentation)
- TASK_GIT_001 (release)
