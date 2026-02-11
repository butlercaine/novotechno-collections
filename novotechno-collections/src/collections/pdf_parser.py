"""
PDF Invoice Parser with Confidence Scoring
Project: PROJ-2026-0210-novotechno-collections
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any
from pathlib import Path

import pdfplumber


@dataclass
class ParsedInvoice:
    """Structured invoice data with confidence scores."""
    invoice_number: str
    client_name: str
    amount: float
    due_date: datetime
    items: List[Dict[str, Any]]
    confidence: float
    confidence_breakdown: Dict[str, float]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "invoice_number": self.invoice_number,
            "client_name": self.client_name,
            "amount": self.amount,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "items": self.items,
            "confidence": self.confidence,
            "confidence_breakdown": self.confidence_breakdown
        }
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


class InvoiceParser:
    """PDF invoice parser with confidence scoring."""
    
    # Field extraction patterns with confidence weights
    INVOICE_NUMBER_PATTERNS = [
        (r"Invoice\s*#?\s*:?\s*([A-Z0-9-]+)", 1.0),     # Exact match
        (r"Factura\s*#?\s*:?\s*([A-Z0-9-]+)", 1.0),    # Spanish
        (r"INV-?([A-Z0-9-]+)", 0.90),                   # INV prefix
        (r"([A-Z]{2,}-\d{4,})", 0.85),                  # Fuzzy pattern
    ]
    
    AMOUNT_PATTERNS = [
        (r"Total[:\s]*\$?([0-9,]+\.?\d*)", 1.0),        # Exact
        (r"Monto[:\s]*\$?([0-9,]+\.?\d*)", 1.0),       # Spanish
        (r"Balance\s+Due[:\s]*\$?([0-9,]+\.?\d*)", 0.95),  # Balance variant
        (r"([0-9,]+\.\d{2})\s*(?:USD|COP|EUR)?", 0.90),  # Fuzzy
    ]
    
    DATE_PATTERNS = [
        (r"Due\s*Date[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", 1.0),
        (r"Fecha\s*de\s*Vencimiento[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", 1.0),
        (r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})", 0.85),      # "15 January 2024"
        (r"(\d{4}-\d{1,2}-\d{1,2})", 0.90),             # ISO format
    ]
    
    def __init__(self):
        """Initialize parser with field weights."""
        self.weights = {
            "invoice_number": 0.30,
            "client_name": 0.25,
            "amount": 0.30,
            "due_date": 0.25,
            "items": 0.10,  # Optional field
        }
        
        # Normalize weights to sum to 1.0 for available fields
        self._normalize_weights()
    
    def _normalize_weights(self):
        """Normalize weights so available fields sum to 1.0."""
        total = sum(self.weights.values())
        if total > 0:
            for field in self.weights:
                self.weights[field] = self.weights[field] / total
    
    def parse(self, pdf_path: str) -> ParsedInvoice:
        """
        Parse invoice PDF and return structured data with confidence.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            ParsedInvoice with extracted data and confidence scores
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        with pdfplumber.open(pdf_path) as pdf:
            text = self._extract_text(pdf)
            
            # Extract fields
            invoice_number = self._extract_field(text, self.INVOICE_NUMBER_PATTERNS)
            client_name = self._extract_client_name(text)
            amount = self._extract_amount(text)
            due_date = self._extract_date(text)
            items = self._extract_items(pdf.pages)
            
            # Build confidence breakdown
            confidence_breakdown = {
                "invoice_number": invoice_number[1],
                "client_name": client_name[1],
                "amount": amount[1],
                "due_date": due_date[1],
                "items": items[1],
            }
            
            # Calculate overall confidence using available fields
            overall_confidence = self._calculate_confidence(confidence_breakdown)
            
            return ParsedInvoice(
                invoice_number=invoice_number[0],
                client_name=client_name[0],
                amount=amount[0],
                due_date=due_date[0],
                items=items[0],
                confidence=overall_confidence,
                confidence_breakdown=confidence_breakdown
            )
    
    def _extract_text(self, pdf) -> str:
        """Extract all text from PDF pages."""
        texts = []
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                texts.append(text)
        return "\n".join(texts)
    
    def _extract_field(self, text: str, patterns: List[Tuple[str, float]]) -> Tuple[Optional[str], float]:
        """
        Extract field using patterns, return value and confidence.
        
        Args:
            text: Text to search
            patterns: List of (regex_pattern, confidence_weight)
            
        Returns:
            Tuple of (value, confidence) or (None, 0.0) if not found
        """
        for pattern, confidence in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                return value, confidence
        return None, 0.0
    
    def _extract_client_name(self, text: str) -> Tuple[Optional[str], float]:
        """Extract client name (usually at top of invoice)."""
        lines = text.split("\n")[:10]  # First 10 lines
        
        # Look for "Bill To:", "Client:", "To:" patterns
        client_patterns = [
            (r"Bill\s+To\s*:?\s*\n(.+?)(?=\n|$)", 0.95),
            (r"Client\s*:?\s*\n(.+?)(?=\n|$)", 0.95),
            (r"To\s*:?\s*\n(.+?)(?=\n|$)", 0.90),
        ]
        
        for pattern, confidence in client_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
            if match:
                value = match.group(1).split("\n")[0].strip()
                return value, confidence
        
        # Fallback: first non-empty, non-keyword line
        for line in lines:
            line = line.strip()
            if len(line) > 3 and not any(kw in line.lower() for kw in ["invoice", "factura", "date", "fecha", "total"]):
                return line, 0.75
        
        return None, 0.0
    
    def _extract_amount(self, text: str) -> Tuple[Optional[float], float]:
        """Extract total amount."""
        value, confidence = self._extract_field(text, self.AMOUNT_PATTERNS)
        if value:
            try:
                cleaned = value.replace(",", "").replace("$", "")
                return float(cleaned), confidence
            except ValueError:
                return None, 0.0
        return None, 0.0
    
    def _extract_date(self, text: str) -> Tuple[Optional[datetime], float]:
        """Extract due date."""
        value, confidence = self._extract_field(text, self.DATE_PATTERNS)
        if value:
            formats = [
                "%m/%d/%Y", "%d/%m/%Y", "%m-%d-%Y", "%d-%m-%Y",
                "%Y-%m-%d", "%d %B %Y", "%Y", "%b %d, %Y"
            ]
            for fmt in formats:
                try:
                    return datetime.strptime(value, fmt), confidence
                except ValueError:
                    continue
        return None, 0.0
    
    def _extract_items(self, pages: List) -> Tuple[List[Dict[str, Any]], float]:
        """Extract line items from PDF tables."""
        items = []
        confidence = 0.0
        
        for page in pages:
            try:
                tables = page.extract_tables()
                for table in tables:
                    # Skip header rows
                    for row in table[1:] if len(table) > 1 else table:
                        if row and len(row) >= 3:
                            try:
                                item = {
                                    "description": str(row[0]) if row[0] else "",
                                    "quantity": float(str(row[1]).replace(",", "")) if len(row) > 1 and row[1] else 1.0,
                                    "price": float(str(row[2]).replace(",", "")) if len(row) > 2 and row[2] else 0.0,
                                    "total": float(str(row[-1]).replace(",", "")) if row[-1] else 0.0,
                                }
                                items.append(item)
                                confidence += 1.0
                            except (ValueError, IndexError, TypeError):
                                continue
            except Exception:
                # Table extraction failed
                continue
        
        item_confidence = min(confidence * 0.1, 1.0) if confidence > 0 else 0.0
        return items, item_confidence
    
    def _calculate_confidence(self, confidence_breakdown: Dict[str, float]) -> float:
        """
        Calculate overall confidence using weighted average.
        
        Args:
            confidence_breakdown: Dict of field -> confidence scores
            
        Returns:
            Overall confidence score between 0 and 1
        """
        total_weight = 0.0
        weighted_sum = 0.0
        
        for field, confidence in confidence_breakdown.items():
            if confidence > 0 and field in self.weights:  # Only include fields that were found
                weight = self.weights[field]
                weighted_sum += confidence * weight
                total_weight += weight
        
        return weighted_sum / total_weight if total_weight > 0 else 0.0


def route_by_confidence(invoice: ParsedInvoice, state_dir: str) -> Dict[str, Any]:
    """
    Route parsed invoice based on confidence score.
    
    Args:
        invoice: ParsedInvoice object
        state_dir: Directory for state files
        
    Returns:
        Dict with routing status and action
    """
    import os
    
    if not os.path.exists(state_dir):
        os.makedirs(state_dir, exist_ok=True)
    
    invoice_id = invoice.invoice_number or "unknown"
    
    if invoice.confidence >= 0.95:
        # Auto-process: high confidence
        auto_dir = os.path.join(state_dir, "auto")
        os.makedirs(auto_dir, exist_ok=True)
        return {"status": "auto", "action": "create_state", "path": auto_dir}
    
    elif invoice.confidence >= 0.85:
        # Review queue: needs human review
        review_dir = os.path.join(state_dir, "review_queue")
        os.makedirs(review_dir, exist_ok=True)
        
        review_path = os.path.join(review_dir, f"{invoice_id}.json")
        with open(review_path, 'w') as f:
            json.dump({
                "invoice": invoice.to_dict(),
                "timestamp": datetime.utcnow().isoformat(),
                "reviewer": None,
                "status": "pending_review"
            }, f, indent=2)
        
        return {"status": "review", "action": "queued_for_review", "path": review_path}
    
    else:
        # Manual processing: confidence too low
        manual_dir = os.path.join(state_dir, "manual")
        os.makedirs(manual_dir, exist_ok=True)
        
        manual_path = os.path.join(manual_dir, f"{invoice_id}.json")
        with open(manual_path, 'w') as f:
            json.dump({
                "invoice": invoice.to_dict(),
                "timestamp": datetime.utcnow().isoformat(),
                "reason": f"Low confidence ({invoice.confidence:.2f})",
                "status": "manual_entry_required"
            }, f, indent=2)
        
        return {"status": "manual", "action": "requires_human", "path": manual_path}


def parse_invoice(pdf_path: str, state_dir: str = "state") -> ParsedInvoice:
    """
    Convenience function to parse and route invoice.
    
    Args:
        pdf_path: Path to PDF file
        state_dir: Directory for state files
        
    Returns:
        ParsedInvoice object
    """
    parser = InvoiceParser()
    invoice = parser.parse(pdf_path)
    routing = route_by_confidence(invoice, state_dir)
    
    print(f"✓ Invoice parsed: {invoice.invoice_number}")
    print(f"  Confidence: {invoice.confidence:.2f}")
    print(f"  Route: {routing['status']}")
    print(f"  Action: {routing['action']}")
    
    return invoice


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python pdf_parser.py <pdf_file> [state_dir]")
        print("Example: python pdf_parser.py invoice.pdf")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    state_dir = sys.argv[2] if len(sys.argv) > 2 else "state/invoices"
    
    try:
        result = parse_invoice(pdf_path, state_dir)
        print("\n📋 Parsed Data:")
        print(result.to_json())
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)