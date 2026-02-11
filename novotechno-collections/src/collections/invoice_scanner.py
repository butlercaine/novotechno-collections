"""Invoice scanner for detecting and processing new invoice PDFs."""

from pathlib import Path
from typing import Dict, List, Optional, Any
import hashlib
import json
from datetime import datetime


class InvoiceScanner:
    """Scan folders for new invoice PDFs."""
    
    def __init__(self, pdf_parser, state_manager, watched_dirs: List[str]):
        """Initialize invoice scanner.
        
        Args:
            pdf_parser: PDF parser instance
            state_manager: State manager instance
            watched_dirs: List of directories to watch
        """
        self.parser = pdf_parser
        self.state = state_manager
        self.watched_dirs = [Path(d) for d in watched_dirs]
        self.known_files = self._load_known_files()
    
    def scan_all(self) -> List[Dict[str, Any]]:
        """Scan all watched directories for new invoices.
        
        Returns:
            List of invoice data dictionaries
        """
        new_invoices = []
        
        for watch_dir in self.watched_dirs:
            if not watch_dir.exists():
                print(f"Warning: Watched directory does not exist: {watch_dir}")
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
        """Check if file is new (not in known_files).
        
        Args:
            filepath: Path to the file
            
        Returns:
            True if file is new, False otherwise
        """
        file_hash = self._hash_file(filepath)
        
        if file_hash in self.known_files:
            return False
        
        # Add to known files
        self.known_files.add(file_hash)
        self._save_known_files()
        return True
    
    def _process_invoice(self, client: str, pdf_path: Path) -> Optional[Dict[str, Any]]:
        """Process new invoice PDF.
        
        Args:
            client: Client name
            pdf_path: Path to PDF file
            
        Returns:
            Invoice data dictionary or None if processing failed
        """
        try:
            # Parse PDF
            parsed = self.parser.parse(str(pdf_path))
            
            # Create state
            state_data = {
                "client": client,
                "number": parsed.invoice_number,
                "email": parsed.email or "",
                "amount": float(parsed.amount) if hasattr(parsed, 'amount') else 0.0,
                "due_date": parsed.due_date.isoformat(),
                "pdf_path": str(pdf_path),
                "confidence": getattr(parsed, 'confidence', 1.0),
                "status": "unpaid",
                "scanned_at": datetime.utcnow().isoformat()
            }
            
            # Route by confidence
            if getattr(parsed, 'confidence', 1.0) >= 0.95:
                self.state.create_invoice(client, parsed.invoice_number, state_data)
            else:
                self.state.queue_for_review(client, parsed.invoice_number, state_data)
            
            return state_data
            
        except Exception as e:
            self.state.log_scan_error(str(pdf_path), str(e))
            return None
    
    def _hash_file(self, filepath: Path) -> str:
        """Hash file for deduplication.
        
        Args:
            filepath: Path to the file
            
        Returns:
            MD5 hash of file contents
        """
        with open(filepath, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    
    def _load_known_files(self) -> set:
        """Load known files from cache.
        
        Returns:
            Set of file hashes
        """
        cache_file = Path.home() / ".cache" / "novotechno-collections" / "known_files.json"
        if cache_file.exists():
            with open(cache_file) as f:
                return set(json.load(f))
        return set()
    
    def _save_known_files(self):
        """Save known files to cache."""
        cache_file = Path.home() / ".cache" / "novotechno-collections" / "known_files.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_file, 'w') as f:
            json.dump(list(self.known_files), f)


class PDFParserStub:
    """Stub PDF parser for testing."""
    
    def __init__(self):
        """Initialize stub parser."""
        self.invoice_counter = 0
    
    def parse(self, pdf_path: str):
        """Parse PDF (stub implementation).
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Parsed invoice object
        """
        from collections import namedtuple
        ParsedInvoice = namedtuple('ParsedInvoice', ['invoice_number', 'due_date', 'amount', 'email', 'confidence'])
        
        self.invoice_counter += 1
        import datetime
        due_date = datetime.datetime.now() + datetime.timedelta(days=7)
        
        return ParsedInvoice(
            invoice_number=f"INV-{self.invoice_counter:05d}",
            due_date=due_date,
            amount=1500.00,
            email="client@example.com",
            confidence=0.98
        )