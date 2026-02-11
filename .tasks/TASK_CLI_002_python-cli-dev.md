# TASK: payment-watcher CLI with fsevents
**Task ID:** TASK_CLI_002
**Owner:** python-cli-dev-novotechno
**Type:** implementation
**Priority:** P0
**Status:** PENDING
**Created:** 2026-02-11 08:00 GMT-5

## Context
Implement the payment-watcher CLI that monitors filesystem for payment notifications (bank CSV exports or confirmation PDFs) using fsevents for real-time detection.

## Requirements

### 1. fsevents Payment Detector
**File:** `novotechno-collections/src/filesystem/payment_detector.py`

**Implementation:**
```python
import time
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from typing import Dict, Callable
from pathlib import Path
import json

class PaymentEventHandler(FileSystemEventHandler):
    """Handle filesystem events for payment detection"""
    
    def __init__(self, state_manager, confidence_checker: Callable):
        self.state = state_manager
        self.check_confidence = confidence_checker
        self.logger = logging.getLogger(__name__)
        self.recent_files = {}  # Track recent events for deduplication
    
    def on_created(self, event):
        if event.is_directory:
            return
        
        # Check for payment file pattern
        if self._is_payment_file(event.src_path):
            self._process_payment_file(event.src_path)
    
    def on_moved(self, event):
        if event.is_directory:
            return
        
        # Detect .pdf.tmp -> .pdf moves (common payment pattern)
        if event.dest_path.endswith(".pdf") and event.src_path.endswith(".pdf.tmp"):
            self._process_payment_file(event.dest_path)
    
    def _is_payment_file(self, filepath: str) -> bool:
        """Check if file matches payment patterns"""
        patterns = [
            r"pagado|paid|payment",
            r"confirmacion|confirmation",
            r"recibo|receipt"
        ]
        import re
        filepath_lower = filepath.lower()
        return any(re.search(p, filepath_lower) for p in patterns)
    
    def _process_payment_file(self, filepath: str):
        """Process detected payment file"""
        # Deduplication: ignore if seen in last 24h
        file_hash = self._hash_file(filepath)
        if self._is_duplicate(file_hash):
            return
        
        self.logger.info(f"💰 Payment file detected: {filepath}")
        
        try:
            # Verify payment matches invoice
            payment_data = self.check_confidence(filepath)
            
            if payment_data["matches_invoice"]:
                # Update state to paid
                self.state.mark_paid(
                    client=payment_data["client"],
                    invoice=payment_data["invoice_number"],
                    payment_data={
                        "method": payment_data.get("method", "unknown"),
                        "amount": payment_data.get("amount", 0),
                        "source_file": filepath,
                        "detected_at": datetime.utcnow().isoformat()
                    }
                )
                
                # Move to archive
                archive_path = self.state.archive_invoice(
                    client=payment_data["client"],
                    invoice=payment_data["invoice_number"],
                    source_file=filepath
                )
                
                # Notify collections-emailer
                self._notify_emailer(
                    invoice=payment_data["invoice_number"],
                    client=payment_data["client"]
                )
                
                self.logger.info(f"✅ Payment processed: {payment_data['invoice_number']}")
            else:
                self.logger.warning(f"⚠️ Payment file doesn't match any invoice: {filepath}")
                
        except Exception as e:
            self.logger.error(f"❌ Error processing payment file: {e}")
    
    def _hash_file(self, filepath: str) -> str:
        """Hash file for deduplication"""
        import hashlib
        with open(filepath, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    
    def _is_duplicate(self, file_hash: str) -> bool:
        """Check if file was processed in last 24h"""
        if file_hash in self.recent_files:
            age = time.time() - self.recent_files[file_hash]
            if age < 86400:  # 24 hours
                return True
        self.recent_files[file_hash] = time.time()
        return False
    
    def _notify_emailer(self, invoice: str, client: str):
        """Notify collections-emailer of payment"""
        message = {
            "type": "INVOICE_PAID",
            "invoice": invoice,
            "client": client,
            "timestamp": datetime.utcnow().isoformat()
        }
        # Write to shared queue or send via sessions_send
        queue_file = Path.home() / ".cache" / "novotechno-collections" / "payment_queue.json"
        queue_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(queue_file, 'a') as f:
            f.write(json.dumps(message) + "\n")

class PaymentDetector:
    """Main payment detection service"""
    
    def __init__(self, state_manager, confidence_checker: Callable):
        self.state = state_manager
        self.check_confidence = confidence_checker
        self.observer = Observer()
        self.handler = PaymentEventHandler(state_manager, confidence_checker)
        self.logger = logging.getLogger(__name__)
    
    def start(self, watch_paths: list):
        """Start watching paths for payment files"""
        for path in watch_paths:
            self.observer.schedule(self.handler, path, recursive=True)
            self.logger.info(f"👀 Watching: {path}")
        
        self.observer.start()
        self.logger.info("🚀 Payment watcher started")
    
    def stop(self):
        """Stop watching"""
        self.observer.stop()
        self.observer.join()
        self.logger.info("🛑 Payment watcher stopped")
```

### 2. Payment Confidence Checker
**File:** `novotechno-collections/src/filesystem/payment_checker.py`

**Implementation:**
```python
from typing import Dict, Optional
from pathlib import Path
import re
from decimal import Decimal

class PaymentConfidenceChecker:
    """Check if payment file matches an invoice"""
    
    def __init__(self, state_manager):
        self.state = state_manager
    
    def __call__(self, payment_file: str) -> Dict:
        """Check payment against unpaid invoices"""
        payment_data = self._extract_payment_data(payment_file)
        
        # Find matching invoice
        matching_invoice = self._find_matching_invoice(
            amount=payment_data.get("amount"),
            client=payment_data.get("client"),
            invoice_number=payment_data.get("invoice_number")
        )
        
        if matching_invoice:
            # Verify amount matches
            amount_match = self._verify_amount(
                payment_data.get("amount"),
                matching_invoice["amount"]
            )
            
            return {
                "matches_invoice": True,
                "client": matching_invoice["client"],
                "invoice_number": matching_invoice["invoice_number"],
                "confidence": amount_match,
                "amount": payment_data.get("amount"),
                "method": payment_data.get("method"),
                "source_file": payment_file
            }
        
        return {
            "matches_invoice": False,
            "source_file": payment_file
        }
    
    def _extract_payment_data(self, filepath: str) -> Dict:
        """Extract payment info from file"""
        data = {
            "amount": None,
            "client": None,
            "invoice_number": None,
            "method": "unknown"
        }
        
        filepath_lower = filepath.lower()
        
        # Extract from filename
        if "bancolombia" in filepath_lower:
            data["method"] = "bancolombia"
        elif "davivienda" in filepath_lower:
            data["method"] = "davivienda"
        elif "transfer" in filepath_lower:
            data["method"] = "transfer"
        
        # Extract amount from filename pattern
        amount_match = re.search(r"[\$]?([0-9,]+\.?\d*)", filepath)
        if amount_match:
            try:
                data["amount"] = float(amount_match.group(1).replace(",", ""))
            except ValueError:
                pass
        
        # Extract invoice number
        invoice_match = re.search(r"(?:factura|invoice|pagare)[\s_-]*([A-Z0-9-]+)", filepath, re.IGNORECASE)
        if invoice_match:
            data["invoice_number"] = invoice_match.group(1)
        
        return data
    
    def _find_matching_invoice(self, amount: float, client: str = None, 
                               invoice_number: str = None) -> Optional[Dict]:
        """Find matching unpaid invoice"""
        unpaid = self.state.get_all_unpaid()
        
        for invoice in unpaid:
            # Match by invoice number first
            if invoice_number and invoice["invoice_number"] == invoice_number:
                return invoice
            
            # Match by amount (within 1% tolerance) if no invoice number
            if amount and client and invoice["client"] == client:
                tolerance = Decimal(str(amount)) * Decimal("0.01")
                invoice_amount = Decimal(str(invoice["amount"]))
                payment_amount = Decimal(str(amount))
                if abs(invoice_amount - payment_amount) <= tolerance:
                    return invoice
        
        return None
    
    def _verify_amount(self, payment_amount: float, invoice_amount: float) -> float:
        """Calculate confidence based on amount match"""
        if payment_amount == invoice_amount:
            return 1.0
        elif payment_amount < invoice_amount:
            # Partial payment
            return 0.95
        elif payment_amount > invoice_amount:
            # Overpayment
            return 0.90
        return 0.0
```

### 3. Message Sender (Inter-Agent)
**File:** `novotechno-collections/src/filesystem/message_sender.py`

**Implementation:**
```python
import json
import logging
from pathlib import Path
from typing import Dict
import time

class InterAgentMessage:
    """Send messages between agents"""
    
    def __init__(self, queue_dir: str = None):
        self.queue_dir = queue_dir or Path.home() / ".cache" / "novotechno-collections" / "queues"
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)
        self.dedupe_window = 86400  # 24 hours
    
    def send(self, recipient: str, message: Dict):
        """Queue message for delivery"""
        queue_file = self.queue_dir / f"{recipient}.jsonl"
        
        # Check deduplication
        if self._is_duplicate(message):
            self.logger.debug(f"⏭️ Duplicate message skipped: {message['type']}")
            return
        
        # Write to queue
        with open(queue_file, 'a') as f:
            f.write(json.dumps({
                **message,
                "_queued_at": time.time()
            }) + "\n")
        
        self.logger.info(f"📨 Message queued for {recipient}: {message['type']}")
    
    def receive(self, recipient: str) -> list:
        """Receive all messages for recipient"""
        queue_file = self.queue_dir / f"{recipient}.jsonl"
        
        if not queue_file.exists():
            return []
        
        messages = []
        with open(queue_file) as f:
            for line in f:
                msg = json.loads(line)
                messages.append(msg)
        
        # Clear queue after reading
        queue_file.unlink()
        
        return messages
    
    def _is_duplicate(self, message: Dict) -> bool:
        """Check if message was sent in deduplication window"""
        msg_hash = self._hash_message(message)
        dedupe_file = self.queue_dir / f"dedupe_{msg_hash}.json"
        
        if dedupe_file.exists():
            age = time.time() - dedupe_file.stat().st_mtime
            if age < self.dedupe_window:
                return True
            dedupe_file.unlink()
        
        # Record message
        with open(dedupe_file, 'w') as f:
            f.write(json.dumps(message))
        
        return False
    
    def _hash_message(self, message: Dict) -> str:
        """Create hash for deduplication"""
        import hashlib
        content = f"{message.get('type')}:{message.get('invoice')}:{message.get('client')}"
        return hashlib.md5(content.encode()).hexdigest()
```

### 4. CLI Entry Point
**File:** `novotechno-collections/scripts/payment-watcher.py`

```python
#!/usr/bin/env python3
import click
import signal
import sys
import time
from src.filesystem.payment_detector import PaymentDetector
from src.filesystem.payment_checker import PaymentConfidenceChecker
from src.filesystem.message_sender import InterAgentMessage

@click.command()
@click.option("--watch-path", multiple=True, help="Paths to watch for payments")
@click.option("--once", is_flag=True, help="Run once and exit")
def main(watch_path: tuple, once: bool):
    """Payment Watcher - Real-time payment detection"""
    
    # Initialize components
    message_sender = InterAgentMessage()
    checker = PaymentConfidenceChecker()
    detector = PaymentDetector(checker)
    
    # Default watch paths
    paths = list(watch_path) or [
        str(Path.home() / "Documents" / "Invoices" / "paid"),
        str(Path.home() / "Downloads"),
    ]
    
    def shutdown_handler(signum, frame):
        click.echo("\n🛑 Shutting down payment watcher...")
        detector.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)
    
    click.echo(f"🚀 Payment Watcher started")
    click.echo(f"👀 Watching: {', '.join(paths)}")
    
    try:
        detector.start(paths)
        
        if once:
            # Just run one cycle
            time.sleep(5)  # Wait for events
            detector.stop()
            return
        
        # Keep running
        while True:
            time.sleep(60)  # Heartbeat
            
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        detector.stop()
        sys.exit(1)

if __name__ == "__main__":
    main()
```

## Dependencies
- watchdog >= 0.9.0 (for fsevents)
- click (already required)

## Output Files
- `novotechno-collections/src/filesystem/__init__.py`
- `novotechno-collections/src/filesystem/payment_detector.py` (250 lines)
- `novotechno-collections/src/filesystem/payment_checker.py` (200 lines)
- `novotechno-collections/src/filesystem/message_sender.py` (150 lines)
- `novotechno-collections/scripts/payment-watcher.py` (100 lines)
- `novotechno-collections/tests/test_payment_detector.py` (100 lines)

## Definition of Done
- [ ] fsevents observer functional
- [ ] Payment detection <30s latency
- [ ] Message sending works
- [ ] All tests pass
- [ ] RESPONSE file written

## Success Criteria
- [ ] Payment detection latency <30s (C-003)
- [ ] State updated correctly on payment
- [ ] Archive move successful
- [ ] Inter-agent message sent to collections-emailer

## Dependencies
- TASK_PDF_002 (state management) - must complete first

## Next Task
TASK_CLI_003 (collections-supervisor) — can run in parallel after this task
