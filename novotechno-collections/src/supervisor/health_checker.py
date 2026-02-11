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
            elif missed_count >= 1:
                self._try_auto_restart(name)
                status.status = "restarting"
            else:
                # First miss - mark unhealthy but don't restart yet
                status.status = "unhealthy"
        
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
            # No log file means first run - return 0, not threshold
            return 0
        
        try:
            with open(log_file) as f:
                lines = f.readlines()
            
            # Count consecutive stale entries
            stale_count = 0
            for line in reversed(lines[-10:]):  # Check last 10 entries
                try:
                    entry = json.loads(line)
                    if entry.get("stale"):
                        stale_count += 1
                    else:
                        break
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue
            
            return stale_count
        except Exception as e:
            # If we can't read the log, treat it as 0 (not at threshold)
            self.logger.error(f"Error reading heartbeat log for {agent_name}: {e}")
            return 0
    
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
            # Log restart attempt
            self.logger.info(f"🔄 Auto-restarting {agent_name}")
            # Implementation note: Would use OpenClaw's sessions_send in production
        except Exception as e:
            self.logger.error(f"❌ Auto-restart failed: {e}")
    
    def _notify_caine(self, message: Dict):
        """Send notification to Caine"""
        # Implementation note: Would use OpenClaw's sessions_send in production
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
        # Would parse QMD ledger in production
        # For now, return mock data for testing
        return {"unpaid": 0, "paid": 0, "escalated": 0}
    
    def _check_queue_health(self) -> Dict:
        """Check queue health"""
        queue_dir = Path.home() / ".cache" / "novotechno-collections" / "queues"
        
        if not queue_dir.exists():
            return {"healthy": True, "queues": []}
        
        queues = {}
        for queue_file in queue_dir.glob("*.jsonl"):
            try:
                with open(queue_file) as f:
                    lines = f.readlines()
                queues[queue_file.stem] = len(lines)
            except Exception as e:
                self.logger.warning(f"Error reading queue {queue_file}: {e}")
        
        return {
            "healthy": all(count < 100 for count in queues.values()),
            "queues": queues
        }
