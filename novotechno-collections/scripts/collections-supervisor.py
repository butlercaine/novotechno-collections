#!/usr/bin/env python3
"""
Collections Supervisor - Monitor agent health and coordinate collections

Usage:
    collections-supervisor --health-check
    collections-supervisor --dashboard --output dashboard.html
    collections-supervisor --agents collections-emailer,payment-watcher
"""

import click
import signal
import sys
import json
import logging
from pathlib import Path
import time
import threading

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from supervisor.health_checker import HealthChecker, StateConsistencyChecker
from supervisor.dashboard import Dashboard, MetricsCollector

# Configure logging
def setup_logging():
    """Setup logging configuration"""
    log_dir = Path.home() / ".cache" / "novotechno-collections"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_dir / "supervisor.log"),
            logging.StreamHandler(sys.stdout)
        ]
    )

@click.command()
@click.option("--health-check", is_flag=True, help="Run health check only")
@click.option("--dashboard", is_flag=True, help="Generate dashboard")
@click.option("--output", type=click.Path(), help="Output file for dashboard")
@click.option("--agents", default="collections-emailer,payment-watcher", help="Comma-separated agent list")
@click.option("--state-dir", type=click.Path(), help="State directory path")
@click.option("--daemon", is_flag=True, help="Run in daemon mode (continuous monitoring)")
@click.option("--interval", default=900, type=int, help="Check interval in seconds (default: 900 = 15min)")
def main(health_check: bool, dashboard: bool, output: str, agents: str, state_dir: str, daemon: bool, interval: int):
    """Collections Supervisor - Agent health and coordination
    
    Monitors agent health, validates state consistency, and generates dashboards.
    """
    
    setup_logging()
    logger = logging.getLogger(__name__)
    
    agent_list = [a.strip() for a in agents.split(",") if a.strip()]
    
    if not agent_list:
        click.echo("❌ No agents specified", err=True)
        sys.exit(1)
    
    # Initialize components
    health_checker = HealthChecker(agent_list)
    
    if state_dir:
        consistency_checker = StateConsistencyChecker(state_dir)
        dashboard_gen = Dashboard(state_dir, health_checker, {})
        metrics = MetricsCollector(state_dir)
    else:
        consistency_checker = StateConsistencyChecker()
        dashboard_gen = Dashboard(consistency_checker.state_dir, health_checker, {})
        metrics = MetricsCollector(consistency_checker.state_dir)
    
    def shutdown_handler(signum, frame):
        """Handle shutdown signals"""
        logger.info("Shutdown signal received")
        click.echo("\n🛑 Supervisor shutting down...")
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)
    
    try:
        if health_check:
            # Run health check only
            logger.info("Running health check")
            click.echo("\n🔍 Running Health Check...\n")
            
            results = health_checker.check_all()
            click.echo("\n💚 Agent Health Status:")
            for name, status in results.items():
                status_emoji = {
                    "healthy": "✅",
                    "unhealthy": "❌",
                    "unknown": "❓",
                    "escalated": "🚨",
                    "restarting": "🔄"
                }.get(status["status"], "❓")
                click.echo(f"{status_emoji} {name}: {status['status']}")
                
                if status.get('errors'):
                    click.echo(f"   Recent errors: {len(status['errors'])}")
            
            # Run state consistency check
            click.echo("\n🔍 State Consistency Check:")
            consistency = consistency_checker.reconcile_all()
            
            ledger_ok = consistency["ledger"]["consistent"]
            queue_ok = consistency["queue"]["healthy"]
            
            click.echo(f"   Ledger: {'✅ Consistent' if ledger_ok else '❌ Mismatch Detected'}")
            click.echo(f"   Queues: {'✅ Healthy' if queue_ok else '❌ Issues Found'}")
            click.echo(f"   Invoice errors: {consistency['invoices']['error_count']}")
            
            if not ledger_ok:
                click.echo("\n   Discrepancies:")
                for disc in consistency["ledger"]["discrepancies"]:
                    click.echo(f"      - {disc['type']}: ledger={disc['ledger']}, state={disc['state']}")
            
            # Show metrics
            click.echo("\n📊 Recent Metrics:")
            recent_metrics = metrics.get_metrics(hours=24)
            for key, value in recent_metrics.items():
                click.echo(f"   {key}: {value}")
            
            # Exit with error code if any agent is unhealthy/escalated
            unhealthy_count = sum(1 for s in results.values() if s["status"] in ["unhealthy", "escalated"])
            if unhealthy_count > 0 or not ledger_ok or not queue_ok:
                logger.warning(f"Health check failed: {unhealthy_count} unhealthy agents")
                sys.exit(1)
            else:
                logger.info("Health check passed")
                click.echo("\n✅ Health check passed")
                sys.exit(0)
        
        elif dashboard:
            # Generate dashboard
            logger.info("Generating dashboard")
            click.echo("📊 Generating dashboard...")
            
            html = dashboard_gen.generate()
            
            if output:
                output_path = Path(output)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, 'w') as f:
                    f.write(html)
                click.echo(f"✅ Dashboard written to: {output}")
                logger.info(f"Dashboard saved to {output}")
            else:
                click.echo(html)
        
        elif daemon:
            # Full supervisor mode - daemon
            logger.info("Starting supervisor daemon")
            click.echo("🚀 Collections Supervisor started (daemon mode)")
            click.echo(f"👀 Monitoring: {', '.join(agent_list)}")
            click.echo(f"⏱️  Check interval: {interval} seconds ({interval/60:.1f} minutes)")
            click.echo("\nPress Ctrl+C to stop\n")
            
            iteration = 0
            while True:
                iteration += 1
                logger.info(f"Health check iteration {iteration}")
                
                try:
                    # Run health check
                    results = health_checker.check_all()
                    
                    # Log any issues
                    issues = []
                    for name, status in results.items():
                        if status['status'] != 'healthy':
                            issues.append(f"{name}: {status['status']}")
                    
                    if issues:
                        click.echo(f"⚠️  Iteration {iteration}: {', '.join(issues)}")
                        logger.warning(f"Health issues: {issues}")
                    else:
                        click.echo(f"✅ Iteration {iteration}: All agents healthy")
                        logger.info("All agents healthy")
                    
                    # Generate dashboard periodically (every 4 iterations = hourly if interval=15min)
                    if iteration % 4 == 0:
                        logger.info("Generating periodic dashboard")
                        dashboard_html = dashboard_gen.generate()
                        dashboard_path = Path.home() / ".cache" / "novotechno-collections" / "dashboard.html"
                        dashboard_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(dashboard_path, 'w') as f:
                            f.write(dashboard_html)
                        logger.info(f"Dashboard updated at {dashboard_path}")
                    
                    # Run state consistency check periodically (every 2 iterations)
                    if iteration % 2 == 0:
                        logger.info("Running state consistency check")
                        consistency = consistency_checker.reconcile_all()
                        if not consistency["ledger"]["consistent"]:
                            logger.error("State inconsistency detected")
                        if not consistency["queue"]["healthy"]:
                            logger.warning("Queue health issues detected")
                    
                except Exception as e:
                    logger.error(f"Error in health check iteration {iteration}: {e}")
                    click.echo(f"❌ Error in iteration {iteration}: {e}", err=True)
                
                # Sleep
                time.sleep(interval)
        
        else:
            # Full supervisor mode - single run
            logger.info("Running supervisor (single execution)")
            click.echo("🚀 Collections Supervisor starting...")
            click.echo(f"👀 Monitoring: {', '.join(agent_list)}")
            
            # Run health check
            results = health_checker.check_all()
            
            click.echo("\n💚 Agent Health Status:")
            for name, status in results.items():
                status_emoji = {
                    "healthy": "✅",
                    "unhealthy": "❌",
                    "unknown": "❓",
                    "escalated": "🚨",
                    "restarting": "🔄"
                }.get(status["status"], "❓")
                click.echo(f"{status_emoji} {name}: {status['status']}")
                
                if status.get('last_heartbeat'):
                    click.echo(f"   Last heartbeat: {status['last_heartbeat'][:19]}")
            
            # Generate dashboard
            dashboard_html = dashboard_gen.generate()
            dashboard_path = Path.home() / ".cache" / "novotechno-collections" / "dashboard.html"
            dashboard_path.parent.mkdir(parents=True, exist_ok=True)
            with open(dashboard_path, 'w') as f:
                f.write(dashboard_html)
            click.echo(f"\n📊 Dashboard saved to: {dashboard_path}")
            
            # Run consistency check
            click.echo("\n🔍 Running state consistency check...")
            consistency = consistency_checker.reconcile_all()
            
            ledger_ok = consistency["ledger"]["consistent"]
            queue_ok = consistency["queue"]["healthy"]
            
            click.echo(f"Ledger: {'✅ Consistent' if ledger_ok else '❌ Mismatch'}")
            click.echo(f"Queues: {'✅ Healthy' if queue_ok else '❌ Issues'}")
            
            click.echo("\n✅ Supervisor run complete")
            logger.info("Supervisor execution completed")
    
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        click.echo(f"\n❌ Fatal error: {e}", err=True)
        sys.exit(1)

if __name__ == "__main__":
    main()

# Test the module is importable
try:
    from supervisor import health_checker, dashboard
    from supervisor.health_checker import AgentHealthStatus, HealthChecker, StateConsistencyChecker
    from supervisor.dashboard import Dashboard, MetricsCollector
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)