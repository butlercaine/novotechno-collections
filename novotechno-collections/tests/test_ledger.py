"""
Unit Tests for QMD Ledger
Project: PROJ-2026-0210-novotechno-collections
"""

import pytest
import tempfile
import json
from pathlib import Path

from src.state.ledger import Ledger, LedgerError


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def ledger(temp_dir):
    """Create Ledger instance with temp directory."""
    ledger_path = temp_dir / "collections.ledger"
    return Ledger(str(ledger_path))


class TestLedgerCreation:
    """Test ledger initialization and creation."""
    
    def test_ledger_created(self, temp_dir):
        """Test ledger file is created on init."""
        ledger_path = temp_dir / "test.ledger"
        ledger = Ledger(str(ledger_path))
        
        assert ledger_path.exists()
        
    def test_ledger_sections_exist(self, ledger):
        """Test required sections are present."""
        content = ledger.ledger_path.read_text()
        
        assert "## Unpaid" in content
        assert "## Paid" in content
        assert "## Escalated" in content
        assert "## Summary" in content
        
    def test_initial_totals_zero(self, ledger):
        """Test initial totals are zero."""
        summary = ledger.get_summary()
        
        assert summary["unpaid_total"] == 0.0
        assert summary["paid_total"] == 0.0
        assert summary["escalated_total"] == 0.0


class TestAddInvoice:
    """Test adding invoices to ledger."""
    
    def test_add_invoice(self, ledger):
        """Test adding invoice to unpaid section."""
        invoice_data = {
            "invoice_number": "INV-001",
            "amount": 1000.0,
            "client_name": "ACME Corp",
            "due_date": "2024-03-15"
        }
        
        result = ledger.add_invoice(invoice_data)
        assert result is True
        
    def test_invoice_appears_in_unpaid(self, ledger):
        """Test invoice appears in unpaid section after adding."""
        invoice_data = {
            "invoice_number": "INV-001",
            "amount": 1000.0,
            "client_name": "ACME Corp"
        }
        
        ledger.add_invoice(invoice_data)
        
        content = ledger.ledger_path.read_text()
        assert "INV-001" in content
        assert "$1,000.00" in content
        
    def test_totals_updated(self, ledger):
        """Test totals are updated after adding invoice."""
        invoice_data = {
            "invoice_number": "INV-001",
            "amount": 1000.0,
            "client_name": "ACME Corp"
        }
        
        ledger.add_invoice(invoice_data)
        
        summary = ledger.get_summary()
        assert summary["unpaid_total"] == 1000.0
        
    def test_duplicate_invoice_raises(self, ledger):
        """Test adding duplicate invoice raises error."""
        invoice_data = {
            "invoice_number": "INV-001",
            "amount": 1000.0,
            "client_name": "ACME Corp"
        }
        
        ledger.add_invoice(invoice_data)
        
        with pytest.raises(LedgerError) as exc_info:
            ledger.add_invoice(invoice_data)
        
        assert "already exists" in str(exc_info.value)
        
    def test_missing_fields_raises(self, ledger):
        """Test missing required fields raises error."""
        with pytest.raises(LedgerError) as exc_info:
            ledger.add_invoice({"invoice_number": "INV-001"})
        
        assert "Missing required fields" in str(exc_info.value)


class TestMarkPaid:
    """Test marking invoices as paid."""
    
    def test_mark_paid_moves_to_paid_section(self, ledger):
        """Test invoice moves from unpaid to paid."""
        invoice_data = {
            "invoice_number": "INV-001",
            "amount": 1000.0,
            "client_name": "ACME Corp"
        }
        
        ledger.add_invoice(invoice_data)
        ledger.mark_paid("INV-001", 1000.0)
        
        content = ledger.ledger_path.read_text()
        assert "INV-001" in content
        assert "Status: paid" in content
        
    def test_totals_updated_on_payment(self, ledger):
        """Test totals are updated when marking paid."""
        invoice_data = {
            "invoice_number": "INV-001",
            "amount": 1000.0,
            "client_name": "ACME Corp"
        }
        
        ledger.add_invoice(invoice_data)
        ledger.mark_paid("INV-001", 1000.0)
        
        summary = ledger.get_summary()
        assert summary["unpaid_total"] == 0.0
        assert summary["paid_total"] == 1000.0
        
    def test_mark_paid_nonexistent_raises(self, ledger):
        """Test marking nonexistent invoice raises error."""
        with pytest.raises(LedgerError) as exc_info:
            ledger.mark_paid("INV-999", 1000.0)
        
        assert "not found" in str(exc_info.value)
        
    def test_mark_paid_with_payment_info(self, ledger):
        """Test mark_paid records payment info."""
        invoice_data = {
            "invoice_number": "INV-001",
            "amount": 1000.0,
            "client_name": "ACME Corp"
        }
        
        ledger.add_invoice(invoice_data)
        ledger.mark_paid("INV-001", 1000.0, payment_method="wire_transfer")
        
        content = ledger.ledger_path.read_text()
        assert "wire_transfer" in content


class TestEscalate:
    """Test escalating invoices."""
    
    def test_escalate_moves_to_escalated_section(self, ledger):
        """Test invoice moves to escalated section."""
        invoice_data = {
            "invoice_number": "INV-001",
            "amount": 1000.0,
            "client_name": "ACME Corp"
        }
        
        ledger.add_invoice(invoice_data)
        ledger.escalate("INV-001", 1000.0, "Non-responsive client")
        
        content = ledger.ledger_path.read_text()
        assert "INV-001" in content
        assert "Status: escalated" in content
        
    def test_escalate_updates_totals(self, ledger):
        """Test totals update on escalation."""
        invoice_data = {
            "invoice_number": "INV-001",
            "amount": 1000.0,
            "client_name": "ACME Corp"
        }
        
        ledger.add_invoice(invoice_data)
        ledger.escalate("INV-001", 1000.0, "Payment declined")
        
        summary = ledger.get_summary()
        assert summary["unpaid_total"] == 0.0
        assert summary["escalated_total"] == 1000.0
        
    def test_escalate_with_reason(self, ledger):
        """Test escalation records reason."""
        invoice_data = {
            "invoice_number": "INV-001",
            "amount": 1000.0,
            "client_name": "ACME Corp"
        }
        
        ledger.add_invoice(invoice_data)
        ledger.escalate("INV-001", 1000.0, "Disputed amount")
        
        content = ledger.ledger_path.read_text()
        assert "Disputed amount" in content


class TestReconciliation:
    """Test ledger reconciliation with state files."""
    
    def test_reconcile_with_state_files(self, temp_dir, ledger):
        """Test reconciliation compares with state files."""
        # Create state file
        state_dir = temp_dir / "state"
        state_dir.mkdir()
        
        state_file = state_dir / "INV-001.json"
        with open(state_file, 'w') as f:
            json.dump({"amount": 1000.0, "status": "unpaid"}, f)
        
        result = ledger.reconcile(str(state_dir))
        
        assert "passed" in result
        assert "state_total" in result
        assert "ledger_total" in result
        
    def test_reconcile_detects_discrepancy(self, temp_dir, ledger):
        """Test reconciliation detects mismatches."""
        # Add invoice to ledger
        invoice_data = {
            "invoice_number": "INV-001",
            "amount": 1000.0,
            "client_name": "ACME Corp"
        }
        ledger.add_invoice(invoice_data)
        
        # Create state with different amount
        state_dir = temp_dir / "state"
        state_dir.mkdir()
        
        state_file = state_dir / "INV-001.json"
        with open(state_file, 'w') as f:
            json.dump({"amount": 500.0, "status": "unpaid"}, f)  # Different amount
        
        result = ledger.reconcile(str(state_dir))
        
        assert result["passed"] is False
        assert result["discrepancy"] == 500.0


class TestSummary:
    """Test ledger summary functionality."""
    
    def test_get_summary(self, ledger):
        """Test getting ledger summary."""
        invoice_data = {
            "invoice_number": "INV-001",
            "amount": 1000.0,
            "client_name": "ACME Corp"
        }
        ledger.add_invoice(invoice_data)
        
        summary = ledger.get_summary()
        
        assert "unpaid_total" in summary
        assert "paid_total" in summary
        assert "escalated_total" in summary
        assert "grand_total" in summary
        
    def test_multiple_invoices(self, ledger):
        """Test ledger with multiple invoices."""
        invoices = [
            {"invoice_number": "INV-001", "amount": 1000.0, "client_name": "ACME"},
            {"invoice_number": "INV-002", "amount": 2000.0, "client_name": "Beta Inc"},
            {"invoice_number": "INV-003", "amount": 500.0, "client_name": "Gamma LLC"},
        ]
        
        for inv in invoices:
            ledger.add_invoice(inv)
        
        summary = ledger.get_summary()
        assert summary["unpaid_total"] == 3500.0
        
    def test_export_json(self, temp_dir, ledger):
        """Test exporting ledger to JSON."""
        invoice_data = {
            "invoice_number": "INV-001",
            "amount": 1000.0,
            "client_name": "ACME Corp"
        }
        ledger.add_invoice(invoice_data)
        
        output_path = temp_dir / "export.json"
        result = ledger.export_json(str(output_path))
        
        assert result.exists()
        
        with open(result) as f:
            data = json.load(f)
        
        assert "export_date" in data
        assert "summary" in data
        assert "sections" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])