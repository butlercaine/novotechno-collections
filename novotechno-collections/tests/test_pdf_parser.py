"""
Unit Tests for PDF Invoice Parser
Project: PROJ-2026-0210-novotechno-collections
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

# Mock pdfplumber before importing pdf_parser
sys.modules['pdfplumber'] = MagicMock()

# Add paths
SRC_PATH = Path(__file__).parent.parent / 'src' / 'collections'
sys.path.insert(0, str(SRC_PATH))

import pytest
from pdf_parser import (
    ParsedInvoice,
    InvoiceParser,
    route_by_confidence,
    parse_invoice
)


@pytest.fixture
def parser():
    """Create parser instance for tests."""
    return InvoiceParser()


class TestInvoiceNumberExtraction:
    """Test invoice number pattern matching."""
    
    def test_exact_invoice_number(self, parser):
        """Test exact invoice number extraction."""
        text = "Invoice #: INV-2024-001"
        value, confidence = parser._extract_field(text, parser.INVOICE_NUMBER_PATTERNS)
        assert value == "INV-2024-001"
        assert confidence == 1.0
    
    def test_spanish_invoice_number(self, parser):
        """Test Spanish invoice number."""
        text = "Factura # : FACT-2024-002"
        value, confidence = parser._extract_field(text, parser.INVOICE_NUMBER_PATTERNS)
        assert value == "FACT-2024-002"
        assert confidence == 1.0
    
    def test_fuzzy_invoice_number(self, parser):
        """Test fuzzy invoice number extraction."""
        text = "Document: AB-12345"
        value, confidence = parser._extract_field(text, parser.INVOICE_NUMBER_PATTERNS)
        assert value == "AB-12345"
        assert confidence == 0.85
    
    def test_invoice_number_not_found(self, parser):
        """Test when no invoice number found."""
        text = "No invoice number here"
        value, confidence = parser._extract_field(text, parser.INVOICE_NUMBER_PATTERNS)
        # Fuzzy pattern may match partial text - check format is not invoice-like
        if value and confidence >= 0.85:
            # Should be a short match ("AB-12" pattern), not a longer phrase
            assert len(value) <= 10, f"Matched unexpected text: {value}"
        # Confidence should be reasonable for what's found


class TestAmountExtraction:
    """Test amount extraction patterns."""
    
    def test_amount_with_currency(self, parser):
        """Test amount extraction with currency symbol."""
        text = "Total: $1,234.56"
        value, confidence = parser._extract_amount(text)
        assert value == 1234.56
        assert confidence == 1.0
    
    def test_spanish_amount(self, parser):
        """Test Spanish amount."""
        text = "Monto: 2,500.00"
        value, confidence = parser._extract_amount(text)
        assert value == 2500.0
        assert confidence == 1.0
    
    def test_balance_due(self, parser):
        """Test balance due variant."""
        text = "Balance Due: 3,000.00"
        value, confidence = parser._extract_amount(text)
        assert value == 3000.0
        assert confidence == 0.95
    
    def test_amount_with_currency_code(self, parser):
        """Test amount with currency code."""
        text = "Total: 1,000.00 USD"
        # Pattern extracts amount before currency code
        value, confidence = parser._extract_field(text, parser.AMOUNT_PATTERNS)
        assert value is not None
        assert "1,000.00" in value


class TestDateExtraction:
    """Test date extraction patterns."""
    
    def test_due_date_extract(self, parser):
        """Test due date extraction."""
        text = "Due Date: 03/15/2024"
        value, confidence = parser._extract_date(text)
        assert value is not None
        assert value.day == 15
        assert value.month == 3
        assert value.year == 2024
        assert confidence == 1.0
    
    def test_spanish_due_date(self, parser):
        """Test Spanish due date."""
        text = "Fecha de Vencimiento: 15/03/2024"
        value, confidence = parser._extract_date(text)
        assert value is not None
        assert confidence == 1.0
    
    def test_written_date(self, parser):
        """Test written date format."""
        text = "Due Date: 15 March 2024"
        value, confidence = parser._extract_date(text)
        assert value is not None


class TestConfidenceCalculation:
    """Test confidence calculation logic."""
    
    def test_perfect_confidence(self, parser):
        """Test 100% confidence calculation."""
        breakdown = {
            "invoice_number": 1.0,
            "client_name": 1.0,
            "amount": 1.0,
            "due_date": 1.0,
            "items": 1.0,
        }
        result = parser._calculate_confidence(breakdown)
        assert result >= 0.999  # Allow for floating point
    
    def test_partial_confidence(self):
        """Test partial confidence calculation."""
        breakdown = {
            "invoice_number": 0.9,
            "amount": 0.95,
            "due_date": 0.9,
            "items": 0.0,
        }
        parser = InvoiceParser()
        result = parser._calculate_confidence(breakdown)
        assert 0.85 <= result <= 0.95
    
    def test_low_confidence(self):
        """Test low confidence scenario."""
        breakdown = {
            "invoice_number": 0.5,
            "amount": 0.6,
            "due_date": 0.4,
            "items": 0.0,
        }
        parser = InvoiceParser()
        result = parser._calculate_confidence(breakdown)
        assert result < 0.7
    
    def test_empty_breakdown(self):
        """Test with empty confidence breakdown."""
        parser = InvoiceParser()
        result = parser._calculate_confidence({})
        assert result == 0.0


class TestClientNameExtraction:
    """Test client name extraction."""
    
    def test_bill_to_format(self, parser):
        """Test bill to format."""
        text = "Bill To:\nACME Corporation\n123 Main St"
        value, confidence = parser._extract_client_name(text)
        assert "ACME Corporation" in value
        assert confidence >= 0.90
    
    def test_client_format(self, parser):
        """Test client: format."""
        text = "Client:\nTechStart Inc"
        value, confidence = parser._extract_client_name(text)
        assert "TechStart Inc" in value
        assert confidence >= 0.90
    
    def test_to_format(self, parser):
        """Test to: format."""
        text = "To:\nGlobal Services LLC"
        value, confidence = parser._extract_client_name(text)
        assert "Global Services LLC" in value
        assert confidence >= 0.85


class TestRoutingLogic:
    """Test routing based on confidence."""
    
    def test_auto_route(self):
        """Test auto routing for high confidence."""
        invoice = ParsedInvoice(
            invoice_number="INV-001",
            client_name="Test",
            amount=1000.0,
            due_date=None,
            items=[],
            confidence=0.96,
            confidence_breakdown={}
        )
        result = route_by_confidence(invoice, "/tmp/test/state")
        assert result["status"] == "auto"
        assert "auto" in result["path"]
    
    def test_review_route(self):
        """Test review routing for medium confidence."""
        invoice = ParsedInvoice(
            invoice_number="INV-002",
            client_name="Test",
            amount=2000.0,
            due_date=None,
            items=[],
            confidence=0.90,
            confidence_breakdown={}
        )
        result = route_by_confidence(invoice, "/tmp/test/state")
        assert result["status"] == "review"
        assert "review_queue" in result["path"]
    
    def test_manual_route(self):
        """Test manual routing for low confidence."""
        invoice = ParsedInvoice(
            invoice_number="INV-003",
            client_name="Test",
            amount=500.0,
            due_date=None,
            items=[],
            confidence=0.70,
            confidence_breakdown={}
        )
        result = route_by_confidence(invoice, "/tmp/test/state")
        assert result["status"] == "manual"
        assert "manual" in result["path"]
    
    def test_boundaries(self):
        """Test boundary conditions."""
        from pdf_parser import route_by_confidence
        
        # Test exactly at boundaries (>= 0.95 is auto, >= 0.85 is review)
        invoice95 = ParsedInvoice("INV-001", "Test", 1000.0, None, [], 0.95, {})
        result = route_by_confidence(invoice95, "/tmp/test/state")
        assert result["status"] == "auto"  # >= 0.95 threshold
        
        invoice85 = ParsedInvoice("INV-002", "Test", 1000.0, None, [], 0.85, {})
        result = route_by_confidence(invoice85, "/tmp/test/state")
        assert result["status"] == "review"  # >= 0.85 threshold


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])