# TASK: PDF Invoice Parser with Confidence Scoring
**Task ID:** TASK_PDF_001
**Owner:** python-cli-dev-novotechno
**Type:** implementation
**Priority:** P0
**Status:** PENDING
**Created:** 2026-02-11 08:00 GMT-5

## Context
Implement PDF invoice parser for extracting invoice data with confidence scoring. Critical for automated collections - low confidence invoices go to manual review.

## Requirements

### 1. PDF Parser Implementation
**File:** `novotechno-collections/src/collections/pdf_parser.py`

**Implementation:**
```python
import pdfplumber
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
from datetime import datetime

@dataclass
class ParsedInvoice:
    invoice_number: str
    client_name: str
    amount: float
    due_date: datetime
    items: List[Dict]
    confidence: float
    confidence_breakdown: Dict[str, float]

class InvoiceParser:
    # Field extraction patterns
    INVOICE_NUMBER_PATTERNS = [
        (r"Invoice\s*#?\s*:?\s*([A-Z0-9-]+)", 1.0),  # Exact match
        (r"Factura\s*#?\s*:?\s*([A-Z0-9-]+)", 1.0),   # Spanish
        (r"([A-Z]{2,}-\d{4,})", 0.85),                 # Fuzzy
    ]
    
    AMOUNT_PATTERNS = [
        (r"Total[:\s]*\$?([0-9,]+\.?\d*)", 1.0),       # Exact
        (r"Monto[:\s]*\$?([0-9,]+\.?\d*)", 1.0),       # Spanish
        (r"([0-9,]+\.\d{2})\s*(?:USD|COP|EUR)?", 0.9),  # Fuzzy
    ]
    
    DATE_PATTERNS = [
        (r"Due\s*Date[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", 1.0),
        (r"Fecha\s*de\s*Vencimiento[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", 1.0),
        (r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})", 0.85),  # "15 January 2024"
    ]
    
    def __init__(self):
        self.weights = {
            "invoice_number": 0.30,
            "amount": 0.30,
            "due_date": 0.25,
            "items": 0.15,
        }
    
    def parse(self, pdf_path: str) -> ParsedInvoice:
        """Parse invoice PDF and return structured data with confidence"""
        
        with pdfplumber.open(pdf_path) as pdf:
            text = self._extract_text(pdf)
            
            invoice_number = self._extract_field(text, self.INVOICE_NUMBER_PATTERNS, "invoice_number")
            client_name = self._extract_client_name(text)
            amount = self._extract_amount(text)
            due_date = self._extract_date(text)
            items = self._extract_items(pdf.pages)
            
            confidence_breakdown = {
                "invoice_number": invoice_number[1],
                "amount": amount[1],
                "due_date": due_date[1],
                "items": items[1],
            }
            
            overall_confidence = sum(
                confidence_breakdown[field] * self.weights[field]
                for field in confidence_breakdown
            )
            
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
        """Extract all text from PDF pages"""
        texts = []
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                texts.append(text)
        return "\n".join(texts)
    
    def _extract_field(self, text: str, patterns: List[Tuple], field_name: str) -> Tuple[Optional[str], float]:
        """Extract field using patterns, return value and confidence"""
        for pattern, confidence in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                return value, confidence
        return None, 0.0
    
    def _extract_client_name(self, text: str) -> Tuple[Optional[str], float]:
        """Extract client name (usually at top of invoice)"""
        lines = text.split("\n")[:5]  # First 5 lines usually have client info
        for line in lines:
            if len(line.strip()) > 3 and not any(kw in line.lower() for kw in ["invoice", "factura", "date", "fecha", "total"]):
                return line.strip(), 0.85
        return None, 0.0
    
    def _extract_amount(self, text: str) -> Tuple[Optional[float], float]:
        """Extract total amount"""
        value, confidence = self._extract_field(text, self.AMOUNT_PATTERNS, "amount")
        if value:
            try:
                cleaned = value.replace(",", "")
                return float(cleaned), confidence
            except ValueError:
                return None, 0.0
        return None, 0.0
    
    def _extract_date(self, text: str) -> Tuple[Optional[datetime], float]:
        """Extract due date"""
        value, confidence = self._extract_field(text, self.DATE_PATTERNS, "due_date")
        if value:
            for fmt in ["%m/%d/%Y", "%d/%m/%Y", "%d-%m-%Y", "%d %B %Y"]:
                try:
                    return datetime.strptime(value, fmt), confidence
                except ValueError:
                    continue
        return None, 0.0
    
    def _extract_items(self, pages: List, min_confidence=0.7) -> Tuple[List[Dict], float]:
        """Extract line items from PDF tables"""
        items = []
        total_confidence = 1.0
        
        for page in pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if row and len(row) >= 3:
                        item = {
                            "description": row[0],
                            "quantity": row[1],
                            "price": row[2],
                        }
                        items.append(item)
                        total_confidence *= 0.95  # Each item adds uncertainty
        
        return items, min(total_confidence, 1.0)
```

### 2. Confidence Routing Logic
**Integration:** After parsing, route based on confidence

```python
def route_by_confidence(invoice: ParsedInvoice, state_dir: str):
    """Route parsed invoice based on confidence score"""
    
    if invoice.confidence >= 0.95:
        # Auto-process: high confidence
        return {"status": "auto", "action": "create_state"}
    
    elif invoice.confidence >= 0.85:
        # Review queue: needs human review
        review_queue_path = f"{state_dir}/review_queue/{invoice.invoice_number}.json"
        with open(review_queue_path, 'w') as f:
            json.dump({
                "invoice": invoice,
                "timestamp": datetime.utcnow().isoformat(),
                "reviewer": None
            }, f, indent=2)
        return {"status": "review", "action": "queued_for_review"}
    
    else:
        # Manual processing: confidence too low
        manual_queue_path = f"{state_dir}/manual/{invoice.invoice_number}.json"
        with open(manual_queue_path, 'w') as f:
            json.dump({
                "invoice": invoice,
                "timestamp": datetime.utcnow().isoformat(),
                "reason": f"Low confidence ({invoice.confidence:.2f})"
            }, f, indent=2)
        return {"status": "manual", "action": "requires_human"}
```

### 3. Unit Tests
**File:** `novotechno-collections/tests/test_pdf_parser.py`

**Test Coverage:**
```python
import pytest
from src.collections.pdf_parser import InvoiceParser, ParsedInvoice

@pytest.fixture
def parser():
    return InvoiceParser()

def test_exact_invoice_number(parser):
    """Test exact invoice number extraction"""
    text = "Invoice #: INV-2024-001"
    value, confidence = parser._extract_field(text, parser.INVOICE_NUMBER_PATTERNS, "invoice_number")
    assert value == "INV-2024-001"
    assert confidence == 1.0

def test_spanish_invoice_number(parser):
    """Test Spanish invoice number"""
    text = "Factura # : FACT-2024-002"
    value, confidence = parser._extract_field(text, parser.INVOICE_NUMBER_PATTERNS, "invoice_number")
    assert value == "FACT-2024-002"
    assert confidence == 1.0

def test_fuzzy_invoice_number(parser):
    """Test fuzzy invoice number extraction"""
    text = "Document: AB-12345"
    value, confidence = parser._extract_field(text, parser.INVOICE_NUMBER_PATTERNS, "invoice_number")
    assert value == "AB-12345"
    assert confidence == 0.85

def test_amount_extraction(parser):
    """Test amount extraction with currency"""
    text = "Total: $1,234.56"
    value, confidence = parser._extract_amount(text)
    assert value == 1234.56
    assert confidence == 1.0

def test_confidence_calculation(parser):
    """Test overall confidence calculation"""
    invoice = ParsedInvoice(
        invoice_number="INV-001",
        client_name="Test Client",
        amount=1000.0,
        due_date=datetime(2024, 3, 15),
        items=[],
        confidence=0.0,
        confidence_breakdown={
            "invoice_number": 1.0,
            "amount": 0.95,
            "due_date": 0.9,
            "items": 0.0
        }
    )
    
    expected = (1.0 * 0.30) + (0.95 * 0.30) + (0.9 * 0.25) + (0.0 * 0.15)
    assert abs(parser._calculate_confidence(invoice) - expected) < 0.01
```

## Dependencies
- pdfplumber >= 0.10.0
- pytest for testing

## Output Files
- `novotechno-collections/src/collections/pdf_parser.py` (300 lines)
- `novotechno-collections/tests/test_pdf_parser.py` (150 lines)
- `novotechno-collections/tests/fixtures/invoices/` (5 test PDFs)

## Definition of Done
- [ ] Code implemented
- [ ] All unit tests pass
- [ ] Parse 5 diverse invoice templates
- [ ] >90% fields extracted correctly
- [ ] Confidence algorithm validated
- [ ] RESPONSE file written

## Success Criteria (from PROJECT_SCOPING)
- [ ] PDF parsing confidence >0.9 on 5 test invoices (C-009)
- [ ] Manual review queue <10% of invoices
- [ ] Confidence scoring: weighted average per spec

## Previous Task
TASK_001 (decomposition) — dependency met
## Next Task
TASK_PDF_002 (atomic state writes) — depends on this task
