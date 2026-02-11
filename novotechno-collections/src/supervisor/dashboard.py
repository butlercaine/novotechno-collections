from datetime import datetime, timedelta
from typing import Dict, List
import json
import logging
from pathlib import Path
from .health_checker import HealthChecker

class Dashboard:
    """Generate HTML dashboard"""
    
    def __init__(self, state_dir: str, health_checker: HealthChecker, config: Dict):
        self.state_dir = Path(state_dir) if isinstance(state_dir, str) else state_dir
        self.health = health_checker
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    def generate(self) -> str:
        """Generate HTML dashboard"""
        health_status = self.health.check_all()
        state_summary = self._get_state_summary()
        metrics = self._collect_metrics()
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>NovotEcho Collections Dashboard</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 20px; background-color: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .status-healthy {{ color: #28a745; font-weight: bold; }}
        .status-unhealthy {{ color: #dc3545; font-weight: bold; }}
        .status-unknown {{ color: #ffc107; font-weight: bold; }}
        .status-escalated {{ color: #6f42c1; font-weight: bold; }}
        .status-restarting {{ color: #17a2b8; font-weight: bold; }}
        table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background-color: #4CAF50; color: white; }}
        tr:nth-child(even) {{ background-color: #f2f2f2; }}
        .metric {{ font-size: 28px; font-weight: bold; color: #333; }}
        .metric-label {{ font-size: 14px; color: #666; }}
        .metric-card {{ background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 10px 0; }}
        .errors {{ background: #f8d7da; padding: 10px; border-radius: 4px; color: #721c24; }}
        .button {{ background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; margin: 5px; }}
        .button:hover {{ background: #0056b3; }}
        h1 {{ color: #333; border-bottom: 3px solid #4CAF50; padding-bottom: 10px; }}
        h2 {{ color: #555; margin-top: 30px; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; }}
        .timestamp {{ color: #666; font-size: 14px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 NovotEcho Collections Dashboard</h1>
            <div class="timestamp">Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</div>
        </div>
        
        <div class="metric-card">
            <div class="metric-label">System Status</div>
            <div class="metric">{"✅ Healthy" if all(s["status"] == "healthy" for s in health_status.values()) else "⚠️ Issues Detected"}</div>
        </div>
        
        <h2>💚 Agent Health</h2>
        {self._render_agent_table(health_status)}
        
        <h2>📈 Performance Metrics (Last 24h)</h2>
        {self._render_metrics_table(metrics)}
        
        <h2>💰 Collection Status</h2>
        {self._render_state_summary(state_summary)}
        
        <h2>⚡ Quick Actions</h2>
        <button class="button" onclick="location.reload()">🔄 Refresh Dashboard</button>
        <button class="button" onclick="alert('Health check triggered (simulation)')">🏥 Run Health Check</button>
        <button class="button" onclick="alert('Metrics collection started (simulation)')">📊 Collect Metrics</button>
        <button class="button" onclick="alert('State reconciliation triggered (simulation)')">🔄 Reconcile State</button>
    </div>
    
    <script>
        // Auto-refresh every 5 minutes
        setTimeout(function(){{
            location.reload();
        }}, 5 * 60 * 1000);
    </script>
</body>
</html>"""
        return html
    
    def _render_agent_table(self, health_status: Dict) -> str:
        """Render agent health table"""
        if not health_status:
            return "<p><em>No agents to monitor</em></p>"
        
        rows = []
        for name, status in health_status.items():
            status_class = f"status-{status['status']}"
            last_heartbeat = status.get('last_heartbeat')
            if last_heartbeat:
                if len(last_heartbeat) > 19:  # ISO format
                    last_heartbeat = last_heartbeat[:19].replace('T', ' ')
            else:
                last_heartbeat = 'N/A'
            
            errors = ""
            if status.get('errors'):
                errors = f"<div class='errors'><strong>Recent Errors:</strong><br>"
                for err in status['errors'][-2:]:  # Show last 2 errors
                    errors += f"• {err.get('reason', 'Unknown error')}<br>"
                errors += "</div>"
            
            rows.append(f"""
            <tr>
                <td><strong>{name}</strong></td>
                <td class="{status_class}">{status['status'].upper()}</td>
                <td>{last_heartbeat}</td>
                <td>{status.get('restarts', 0)}</td>
            </tr>
            <tr>
                <td colspan="4" style="padding-top: 0; padding-bottom: 10px;">
                    {errors}
                </td>
            </tr>
            """)
        
        return f"""
        <table>
            <tr><th>Agent</th><th>Status</th><th>Last Heartbeat</th><th>Restarts</th></tr>
            {''.join(rows)}
        </table>
        """
    
    def _render_metrics_table(self, metrics: Dict) -> str:
        """Render performance metrics table"""
        return f"""
        <table>
            <tr><th>Metric</th><th>Value</th><th>Description</th></tr>
            <tr><td>📧 Emails Sent</td><td class="metric">{metrics['emails_sent']}</td><td>Total collection emails sent</td></tr>
            <tr><td>💰 Payments Detected</td><td class="metric">{metrics['payments_detected']}</td><td>Payments automatically detected</td></tr>
            <tr><td>❌ Errors</td><td class="metric">{metrics['errors']}</td><td>System errors encountered</td></tr>
            <tr><td>⏱️ Avg Latency</td><td class="metric">{metrics['avg_latency']:.1f}h</td><td>Average payment detection time</td></tr>
        </table>
        """
    
    def _render_state_summary(self, summary: Dict) -> str:
        """Render state summary"""
        return f"""
        <table>
            <tr><th>Status</th><th>Count</th><th>Total Amount</th><th>Change (24h)</th></tr>
            <tr><td>🔴 Unpaid</td><td class="metric">{summary['unpaid_count']}</td><td class="metric">${summary['unpaid_total']:,.2f}</td><td>{summary['unpaid_change']:+d}</td></tr>
            <tr><td>🟢 Paid</td><td class="metric">{summary['paid_count']}</td><td class="metric">${summary['paid_total']:,.2f}</td><td>{summary['paid_change']:+d}</td></tr>
            <tr><td>🟠 Escalated</td><td class="metric">{summary['escalated_count']}</td><td class="metric">${summary['escalated_total']:,.2f}</td><td>{summary['escalated_change']:+d}</td></tr>
            <tr><td>🟡 In Review</td><td class="metric">{summary['review_count']}</td><td>-</td><td>{summary['review_change']:+d}</td></tr>
        </table>
        """
    
    def _get_state_summary(self) -> Dict:
        """Get state summary metrics"""
        unpaid_count, unpaid_total = 0, 0
        paid_count, paid_total = 0, 0
        escalated_count, escalated_total = 0, 0
        review_count = 0
        
        if self.state_dir.exists():
            try:
                for state_file in self.state_dir.rglob("*.json"):
                    if "archive" in str(state_file):
                        continue
                    
                    try:
                        with open(state_file) as f:
                            data = json.load(f)
                        
                        status = data.get("status", "unknown")
                        amount = data.get("amount", 0)
                        
                        if status == "unpaid":
                            unpaid_count += 1
                            unpaid_total += amount
                        elif status == "paid":
                            paid_count += 1
                            paid_total += amount
                        elif status == "escalated":
                            escalated_count += 1
                            escalated_total += amount
                        elif status == "review":
                            review_count += 1
                            
                    except Exception as e:
                        self.logger.error(f"Error reading {state_file}: {e}")
            except Exception as e:
                self.logger.error(f"Error scanning state directory: {e}")
        
        # Read changes from cache
        change_cache = Path.home() / ".cache" / "novotechno-collections" / "state_changes.json"
        changes = {"unpaid": 0, "paid": 0, "escalated": 0, "review": 0}
        
        if change_cache.exists():
            try:
                with open(change_cache) as f:
                    cached = json.load(f)
                    # Only use recent changes (within 24 hours)
                    cutoff = (datetime.utcnow() - timedelta(days=1)).isoformat()
                    for k, v in cached.items():
                        if isinstance(v, dict) and v.get("timestamp", "") > cutoff:
                            changes[k] = v.get("change", 0)
            except Exception as e:
                self.logger.warning(f"Error reading change cache: {e}")
        
        return {
            "unpaid_count": unpaid_count,
            "unpaid_total": unpaid_total,
            "unpaid_change": changes["unpaid"],
            "paid_count": paid_count,
            "paid_total": paid_total,
            "paid_change": changes["paid"],
            "escalated_count": escalated_count,
            "escalated_total": escalated_total,
            "escalated_change": changes["escalated"],
            "review_count": review_count,
            "review_change": changes["review"]
        }
    
    def _collect_metrics(self) -> Dict:
        """Collect current metrics"""
        metrics_collector = MetricsCollector(str(self.state_dir))
        return metrics_collector.get_metrics(hours=24)

class MetricsCollector:
    """Collect metrics for reporting"""
    
    def __init__(self, state_dir: str = None):
        if state_dir is None:
            self.state_dir = Path.home() / ".local" / "share" / "novotechno-collections" / "state"
        else:
            self.state_dir = Path(state_dir)
        self.logger = logging.getLogger(__name__)
    
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
        # Read from email log
        email_log = Path.home() / ".cache" / "novotechno-collections" / "email_activity.log"
        count = 0
        
        if email_log.exists():
            try:
                with open(email_log) as f:
                    for line in f:
                        try:
                            entry = json.loads(line.strip())
                            timestamp = datetime.fromisoformat(entry.get("timestamp", "").replace('Z', '+00:00'))
                            if timestamp >= since and entry.get("type") == "EMAIL_SENT":
                                count += 1
                        except Exception:
                            continue
            except Exception as e:
                self.logger.warning(f"Error reading email log: {e}")
        
        return count
    
    def _count_payments(self, since: datetime) -> int:
        """Count payments detected"""
        # Read from payment log
        payment_log = Path.home() / ".cache" / "novotechno-collections" / "payment_activity.log"
        count = 0
        
        if payment_log.exists():
            try:
                with open(payment_log) as f:
                    for line in f:
                        try:
                            entry = json.loads(line.strip())
                            timestamp = datetime.fromisoformat(entry.get("timestamp", "").replace('Z', '+00:00'))
                            if timestamp >= since and entry.get("type") == "PAYMENT_DETECTED":
                                count += 1
                        except Exception:
                            continue
            except Exception as e:
                self.logger.warning(f"Error reading payment log: {e}")
        
        return count
    
    def _count_errors(self, since: datetime) -> int:
        """Count errors"""
        error_log = Path.home() / ".cache" / "novotechno-collections" / "error.log"
        count = 0
        
        if error_log.exists():
            try:
                with open(error_log) as f:
                    for line in f:
                        try:
                            entry = json.loads(line.strip())
                            timestamp = datetime.fromisoformat(entry.get("timestamp", "").replace('Z', '+00:00'))
                            if timestamp >= since and entry.get("level") in ["ERROR", "CRITICAL"]:
                                count += 1
                        except Exception:
                            continue
            except Exception as e:
                self.logger.warning(f"Error reading error log: {e}")
        
        return count
    
    def _avg_payment_latency(self, since: datetime) -> float:
        """Average payment detection latency in hours"""
        # This would read from state files and calculate time difference
        # For now, return a placeholder value
        return 2.5