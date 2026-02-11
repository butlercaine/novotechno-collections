# TASK: collections-emailer CLI
**Task ID:** TASK_CLI_001
**Owner:** python-cli-dev-novotechno
**Type:** implementation
**Priority:** P0
**Status:** PENDING
**Created:** 2026-02-11 08:00 GMT-5

## Context
Implement the collections-emailer CLI agent that monitors Gmail, extracts invoices, and sends Spanish collection reminder emails via Microsoft Graph API.

## Requirements

### 1. Email Scheduler
**File:** `novotechno-collections/src/collections/scheduler.py`

**Implementation:**
```python
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json
from pathlib import Path

class CollectionScheduler:
    """Schedule and send collection reminder emails"""
    
    REMINDER_RULES = {
        "reminder_1": {"days_before_due": 3, "template": "reminder_3d"},
        "reminder_2": {"days_before_due": 0, "template": "reminder_due"},
        "overdue_1": {"days_after_due": 5, "template": "overdue_5d"},
        "overdue_2": {"days_after_due": 7, "template": "overdue_7d"},
        "final_notice": {"days_after_due": 10, "template": "final_notice"},
        "escalation": {"days_after_due": 14, "template": "escalation"},
    }
    
    def __init__(self, email_sender, state_manager):
        self.sender = email_sender
        self.state = state_manager
    
    def get_due_reminders(self) -> List[Dict]:
        """Get list of invoices needing reminders today"""
        reminders = []
        
        for invoice in self.state.get_all_unpaid():
            due_date = datetime.fromisoformat(invoice["due_date"])
            days_until_due = (due_date - datetime.now()).days
            
            for rule_name, rule in self.REMINDER_RULES.items():
                if days_until_due == -rule["days_before_due"]:  # Before due
                    reminders.append({
                        "invoice": invoice,
                        "rule": rule_name,
                        "template": rule["template"],
                        "days_until_due": days_until_due
                    })
                elif days_until_due == rule["days_after_due"]:  # After due
                    reminders.append({
                        "invoice": invoice,
                        "rule": rule_name,
                        "template": rule["template"],
                        "days_overdue": abs(days_until_due)
                    })
        
        return reminders
    
    def send_reminders(self, batch_size=20) -> Dict:
        """Send reminders, respecting rate limits"""
        reminders = self.get_due_reminders()
        sent = 0
        failed = 0
        rate_limited = 0
        
        for reminder in reminders[:batch_size]:
            try:
                # Check if client opted out
                if self.state.is_paused(reminder["invoice"]["client"]):
                    continue
                
                # Render and send email
                self.sender.send_collection_reminder(
                    to=reminder["invoice"]["email"],
                    template=reminder["template"],
                    invoice_data=reminder["invoice"]
                )
                
                # Update state
                self.state.record_email_sent(
                    reminder["invoice"]["client"],
                    reminder["invoice"]["number"],
                    reminder["rule"]
                )
                
                sent += 1
                
            except RateLimitExceeded:
                rate_limited += 1
                break  # Stop sending, will resume next cycle
                
            except Exception as e:
                failed += 1
                self.state.record_email_failed(
                    reminder["invoice"]["client"],
                    reminder["invoice"]["number"],
                    reminder["rule"],
                    str(e)
                )
        
        return {"sent": sent, "failed": failed, "rate_limited": rate_limited}
```

### 2. Reply Monitor
**File:** `novotechno-collections/src/collections/reply_monitor.py`

**Implementation:**
```python
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
import re

@dataclass
class ReplyAction:
    action: str  # "pause", "manual_review", "escalate"
    client: str
    invoice: str
    reason: str

class ReplyMonitor:
    """Monitor inbox for client replies"""
    
    REPLY_PATTERNS = {
        r"stop|detener|unsubscribe": "pause",
        r"pagado|pago|paid|paid?:": "mark_paid",
        r"dudas|pregunta|question|clarify": "manual_review",
    }
    
    def __init__(self, graph_client, state_manager):
        self.graph = graph_client
        self.state = state_manager
        self.last_check = None
    
    def check_replies(self) -> List[ReplyAction]:
        """Check inbox for replies to collection emails"""
        replies = []
        
        # Get messages since last check
        messages = self.graph.get_messages(
            received_after=self.last_check,
            sender_addresses=self._get_collection_senders()
        )
        
        for message in messages:
            action = self._parse_reply(message)
            if action:
                replies.append(action)
        
        self.last_check = datetime.utcnow().isoformat()
        return replies
    
    def _parse_reply(self, message: Dict) -> Optional[ReplyAction]:
        """Parse reply and determine action"""
        subject = message.get("subject", "")
        body = message.get("body", {}).get("content", "")
        content = f"{subject} {body}".lower()
        
        # Extract invoice number
        invoice_match = re.search(r"factura\s*#?\s*:?\s*([A-Z0-9-]+)", content, re.IGNORECASE)
        if not invoice_match:
            invoice_match = re.search(r"invoice\s*#?\s*:?\s*([A-Z0-9-]+)", content, re.IGNORECASE)
        
        invoice_number = invoice_match.group(1) if invoice_match else None
        
        # Determine action
        for pattern, action in self.REPLY_PATTERNS.items():
            if re.search(pattern, content):
                return ReplyAction(
                    action=action,
                    client=message.get("from", {}).get("emailAddress", {}).get("address", ""),
                    invoice=invoice_number or "unknown",
                    reason=f"Matched pattern: {pattern}"
                )
        
        return None
    
    def execute_actions(self, actions: List[ReplyAction]):
        """Execute reply actions"""
        for action in actions:
            if action.action == "pause":
                self.state.pause_collection(action.client)
                self._notify_account_manager(action)
                
            elif action.action == "mark_paid":
                self.state.mark_paid_by_reply(action.client, action.invoice)
                
            elif action.action == "manual_review":
                self.state.queue_for_review(action.client, action.invoice)
    
    def _notify_account_manager(self, action: ReplyAction):
        """Notify account manager of opt-out"""
        # Implementation for notifying account manager
        pass
```

### 3. Invoice Scanner
**File:** `novotechno-collections/src/collections/invoice_scanner.py`

**Implementation:**
```python
from pathlib import Path
from typing import Dict, List
import hashlib
import json

class InvoiceScanner:
    """Scan folders for new invoice PDFs"""
    
    def __init__(self, pdf_parser, state_manager, watched_dirs: List[str]):
        self.parser = pdf_parser
        self.state = state_manager
        self.watched_dirs = [Path(d) for d in watched_dirs]
        self.known_files = self._load_known_files()
    
    def scan_all(self) -> List[Dict]:
        """Scan all watched directories for new invoices"""
        new_invoices = []
        
        for watch_dir in self.watched_dirs:
            if not watch_dir.exists():
                continue
                
            for client_dir in watch_dir.iterdir():
                if not client_dir.is_dir():
                    continue
                    
                for pdf_file in client_dir.glob("*.pdf"):
                    if self._is_new_file(pdf_file):
                        invoice_data = self._process_invoice(client_dir.name, pdf_file)
                        if invoice_data:
                            new_invoices.append(invoice_data)
        
        return new_invoices
    
    def _is_new_file(self, filepath: Path) -> bool:
        """Check if file is new (not in known_files)"""
        file_hash = self._hash_file(filepath)
        
        if file_hash in self.known_files:
            return False
        
        # Add to known files
        self.known_files.add(file_hash)
        self._save_known_files()
        return True
    
    def _process_invoice(self, client: str, pdf_path: Path) -> Optional[Dict]:
        """Process new invoice PDF"""
        try:
            # Parse PDF
            parsed = self.parser.parse(str(pdf_path))
            
            # Create state
            state_data = {
                "client": client,
                "invoice_number": parsed.invoice_number,
                "amount": parsed.amount,
                "due_date": parsed.due_date.isoformat(),
                "pdf_path": str(pdf_path),
                "confidence": parsed.confidence,
                "status": "unpaid",
                "scanned_at": datetime.utcnow().isoformat()
            }
            
            # Route by confidence
            if parsed.confidence >= 0.95:
                self.state.create_invoice(client, parsed.invoice_number, state_data)
            else:
                self.state.queue_for_review(client, parsed.invoice_number, state_data)
            
            return state_data
            
        except Exception as e:
            self.state.log_scan_error(str(pdf_path), str(e))
            return None
    
    def _hash_file(self, filepath: Path) -> str:
        """Hash file for deduplication"""
        with open(filepath, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    
    def _load_known_files(self) -> set:
        """Load known files from cache"""
        cache_file = Path.home() / ".cache" / "novotechno-collections" / "known_files.json"
        if cache_file.exists():
            with open(cache_file) as f:
                return set(json.load(f))
        return set()
    
    def _save_known_files(self):
        """Save known files to cache"""
        cache_file = Path.home() / ".cache" / "novotechno-collections" / "known_files.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_file, 'w') as f:
            json.dump(list(self.known_files), f)
```

### 4. CLI Entry Point
**File:** `novotechno-collections/scripts/collections-emailer.py`

```python
#!/usr/bin/env python3
import click
import signal
import sys
import time
from src.collections.scheduler import CollectionScheduler
from src.collections.reply_monitor import ReplyMonitor
from src.collections.invoice_scanner import InvoiceScanner
from src.auth.token_validator import TokenValidator
from src.collections.email_sender import GraphEmailSender

@click.command()
@click.option("--dry-run", is_flag=True, help="Don't actually send emails")
@click.option("--once", is_flag=True, help="Run once and exit")
def main(dry_run: bool, once: bool):
    """Collections Emailer - Automated invoice collection reminders"""
    
    # Initialize components
    validator = TokenValidator()
    sender = GraphEmailSender(validator)
    scheduler = CollectionScheduler(sender)
    monitor = ReplyMonitor()
    scanner = InvoiceScanner()
    
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
        while True:
            # Scan for new invoices
            new_invoices = scanner.scan_all()
            if new_invoices:
                click.echo(f"📄 Found {len(new_invoices)} new invoices")
            
            # Send reminders
            result = scheduler.send_reminders()
            if result["sent"] > 0:
                click.echo(f"📧 Sent {result['sent']} reminders")
            if result["rate_limited"] > 0:
                click.echo(f"⚠️ Rate limited: {result['rate_limited']}")
            
            # Check for replies
            actions = monitor.check_replies()
            if actions:
                click.echo(f"📬 Processing {len(actions)} reply actions")
                monitor.execute_actions(actions)
            
            if once:
                break
            
            # Heartbeat cycle: 30 minutes
            click.echo("💤 Sleeping for 30 minutes...")
            time.sleep(1800)  # 30 minutes
            
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
```

## Dependencies
- click >= 8.0
- APScheduler (for future scheduling flexibility)
- Already have: pdfplumber, requests, msal

## Output Files
- `novotechno-collections/src/collections/scheduler.py` (300 lines)
- `novotechno-collections/src/collections/reply_monitor.py` (250 lines)
- `novotechno-collections/src/collections/invoice_scanner.py` (200 lines)
- `novotechno-collections/scripts/collections-emailer.py` (100 lines)
- `novotechno-collections/tests/test_scheduler.py` (120 lines)
- `novotechno-collections/tests/test_reply_monitor.py` (100 lines)

## Definition of Done
- [ ] All 4 sub-modules implemented
- [ ] CLI entry point works
- [ ] Rate limiting enforced
- [ ] Reply detection works
- [ ] All tests pass
- [ ] RESPONSE file written

## Success Criteria
- [ ] Emails sent on correct schedule (T-3d, due, T+5d, T+7d, T+10d, T+14d)
- [ ] Rate limiting (20/cycle) enforced
- [ ] Reply detection (STOP, PAGADO, DUDAS) functional
- [ ] Graceful shutdown on SIGTERM

## Dependencies
- TASK_OAUTH_002 (Graph API client) - must complete first
- TASK_PDF_002 (state management) - must complete first

## Next Task
TASK_CLI_002 (payment-watcher) — can run in parallel after PDF_002
