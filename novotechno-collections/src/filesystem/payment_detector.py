import time
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from typing import Dict, Callable
from pathlib import Path
import json
import hashlib
import re
from datetime import datetime

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
        try:
            with open(filepath, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception as e:
            self.logger.warning(f"Could not hash file {filepath}: {e}")
            return filepath  # Fall back to filepath as identifier
    
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
            path_obj = Path(path)
            if path_obj.exists():
                self.observer.schedule(self.handler, str(path_obj), recursive=True)
                self.logger.info(f"👀 Watching: {path}")
            else:
                self.logger.warning(f"⚠️ Path does not exist: {path}")
        
        self.observer.start()
        self.logger.info("🚀 Payment watcher started")
    
    def stop(self):
        """Stop watching"""
        self.observer.stop()
        self.observer.join()
        self.logger.info("🛑 Payment watcher stopped")