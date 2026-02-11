#!/usr/bin/env python3
"""Collections Emailer - Automated invoice collection reminders CLI."""

import click
import signal
import sys
import time
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from collections.scheduler import CollectionScheduler, RateLimitExceeded
from collections.reply_monitor import ReplyMonitor
from collections.invoice_scanner import InvoiceScanner
from collections.pdf_parser import PDFParser
from state.ledger import Ledger


class GraphEmailSender:
    """Stub email sender for collections."""
    
    def __init__(self, validator):
        """Initialize email sender.
        
        Args:
            validator: Token validator
        """
        self.validator = validator
        self.sent_count = 0
    
    def send_collection_reminder(self, to: str, template: str, invoice_data: dict):
        """Send a collection reminder email.
        
        Args:
            to: Recipient email
            template: Template name
            invoice_data: Invoice data dictionary
        """
        if self.sent_count >= 20:
            raise RateLimitExceeded("Rate limit exceeded")
        
        print(f"[EMAIL] Sending {template} to {to} for invoice {invoice_data.get('number', 'N/A')}")
        self.sent_count += 1
        
        # In real implementation, this would call Graph API
        return {"status": "sent", "message_id": f"msg-{self.sent_count}"}


class TokenValidator:
    """Stub token validator."""
    
    def __init__(self):
        """Initialize token validator."""
        pass
    
    def validate(self):
        """Validate authentication token."""
        return True


@click.command()
@click.option("--dry-run", is_flag=True, help="Don't actually send emails")
@click.option("--once", is_flag=True, help="Run once and exit")
@click.option("--watch-dir", "-w", multiple=True, help="Directories to watch for invoices")
@click.option("--config", "-c", type=click.Path(), help="Configuration file path")
def main(dry_run: bool, once: bool, watch_dir, config):
    """Collections Emailer - Automated invoice collection reminders."""
    
    # Initialize components
    validator = TokenValidator()
    sender = GraphEmailSender(validator)
    
    # Initialize state manager (ledger)
    state_file = Path.home() / ".cache" / "novotechno-collections" / "collection_state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state = Ledger(str(state_file))
    
    # Initialize scheduler
    scheduler = CollectionScheduler(sender, state)
    
    # Initialize reply monitor
    graph_client = None  # Would be Graph API client
    monitor = ReplyMonitor(graph_client, state)
    
    # Initialize invoice scanner
    parser = PDFParser()
    watch_directories = list(watch_dir) if watch_dir else [str(Path.home() / "invoices")]
    scanner = InvoiceScanner(parser, state, watch_directories)
    
    # Graceful shutdown handler
    def shutdown_handler(signum, frame):
        click.echo("\n🛑 Shutting down gracefully...")
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)
    
    click.echo(f"🚀 Collections Emailer started (dry_run={dry_run})")
    
    if dry_run:
        click.echo("🔍 DRY RUN MODE - No emails will be sent")
    
    try:
        cycle_count = 0
        while True:
            cycle_count += 1
            click.echo(f"\n📊 Cycle #{cycle_count} - {datetime.now()}")
            
            # Scan for new invoices
            try:
                new_invoices = scanner.scan_all()
                if new_invoices:
                    click.echo(f"📄 Found {len(new_invoices)} new invoices")
                    for inv in new_invoices:
                        click.echo(f"   - {inv['client']}: {inv['number']} (${inv['amount']:.2f})")
            except Exception as e:
                click.echo(f"❌ Error scanning invoices: {e}", err=True)
            
            # Send reminders
            try:
                result = scheduler.send_reminders(batch_size=20)
                if result["sent"] > 0:
                    click.echo(f"📧 Sent {result['sent']} reminders")
                if result["failed"] > 0:
                    click.echo(f"❌ Failed to send {result['failed']} reminders")
                if result["rate_limited"] > 0:
                    click.echo(f"⚠️  Rate limited: {result['rate_limited']}")
            except Exception as e:
                click.echo(f"❌ Error sending reminders: {e}", err=True)
            
            # Check for replies
            try:
                actions = monitor.check_replies()
                if actions:
                    click.echo(f"📬 Processing {len(actions)} reply actions")
                    monitor.execute_actions(actions)
                    for action in actions:
                        click.echo(f"   - {action.action}: {action.client}")
            except Exception as e:
                click.echo(f"❌ Error checking replies: {e}", err=True)
            
            if once:
                click.echo("✅ Single run completed")
                break
            
            # Heartbeat cycle: 30 minutes
            click.echo("💤 Sleeping for 30 minutes...")
            time.sleep(1800)  # 30 minutes
            
    except Exception as e:
        click.echo(f"❌ Fatal error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()