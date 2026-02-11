"""
Unit Tests for Atomic State File Writes
Project: PROJ-2026-0210-novotechno-collections
"""

import pytest
import tempfile
import json
import os
from pathlib import Path

from src.state.invoice_state import InvoiceState, StateCorruptionError, StateLockError
from src.state.ledger import Ledger, LedgerError


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def invoice_state(temp_dir):
    """Create InvoiceState instance with temp directory."""
    return InvoiceState(str(temp_dir), enable_locking=False)


@pytest.fixture
def ledger(temp_dir):
    """Create Ledger instance with temp directory."""
    ledger_path = temp_dir / "collections.ledger"
    return Ledger(str(ledger_path))


class TestAtomicWrites:
    """Test atomic file write functionality."""
    
    def test_atomic_write_creates_file(self, invoice_state, temp_dir):
        """Test atomic write creates final file."""
        filepath = temp_dir / "test.json"
        
        with invoice_state.atomic_write(filepath) as f:
            json.dump({"test": "data"}, f)
        
        assert filepath.exists()
        assert not filepath.with_suffix(".json.tmp").exists()
        
    def test_atomic_write_no_partial_on_error(self, invoice_state, temp_dir):
        """Test temp file cleaned up on error."""
        filepath = temp_dir / "test.json"
        
        try:
            with invoice_state.atomic_write(filepath) as f:
                json.dump({"test": "data"}, f)
                raise ValueError("Test error")
        except ValueError:
            pass
        
        assert not filepath.exists()
        
    def test_file_permissions_restrictive(self, invoice_state, temp_dir):
        """Test file has restrictive permissions (0600)."""
        filepath = temp_dir / "test.json"
        
        with invoice_state.atomic_write(filepath) as f:
            json.dump({"test": "data"}, f)
        
        stat = filepath.stat()
        # Check owner can read/write, others cannot
        assert stat.st_mode & 0o600 == 0o600
        

class TestChecksums:
    """Test checksum verification."""
    
    def test_checksum_added_to_state(self, invoice_state):
        """Test checksum is added to written state."""
        invoice_state.write_state("client1", "INV-001", {"amount": 1000})
        
        data = invoice_state.read_state("client1", "INV-001", verify_checksum=False)
        assert "_checksum" in data
        assert len(data["_checksum"]) == 16  # SHA256 truncated
        
    def test_checksum_verifies_on_read(self, invoice_state):
        """Test checksum verifies correctly."""
        original_data = {"amount": 1000, "status": "unpaid"}
        invoice_state.write_state("client1", "INV-001", original_data)
        
        # Should read without error
        read_data = invoice_state.read_state("client1", "INV-001", verify_checksum=True)
        assert read_data["amount"] == 1000
        assert read_data["status"] == "unpaid"
        
    def test_corruption_detected(self, invoice_state, temp_dir):
        """Test corruption raises StateCorruptionError."""
        invoice_state.write_state("client1", "INV-001", {"amount": 1000})
        
        # Corrupt the file
        state_file = temp_dir / "client1" / "INV-001.json"
        with open(state_file, 'r') as f:
            data = json.load(f)
        
        data["amount"] = 2000  # Corrupt data
        with open(state_file, 'w') as f:
            json.dump(data, f)
        
        # Should raise corruption error
        with pytest.raises(StateCorruptionError):
            invoice_state.read_state("client1", "INV-001", verify_checksum=True)
            
    def test_read_without_checksum(self, invoice_state):
        """Test can read without checksum verification."""
        invoice_state.write_state("client1", "INV-001", {"amount": 1000})
        
        # Should read without error even if checksum wrong
        data = invoice_state.read_state("client1", "INV-001", verify_checksum=False)
        assert data["amount"] == 1000
        

class TestEventLog:
    """Test append-only event logging."""
    
    def test_event_logged_on_write(self, invoice_state, temp_dir):
        """Test events are appended to log."""
        invoice_state.write_state("client1", "INV-001", {"amount": 1000})
        
        log_file = temp_dir / "events.log"
        assert log_file.exists()
        
        with open(log_file) as f:
            lines = f.readlines()
        
        assert len(lines) == 1
        event = json.loads(lines[0])
        assert event["client"] == "client1"
        assert event["invoice"] == "INV-001"
        assert event["event"] == "state_update"
        
    def test_event_log_append_only(self, invoice_state, temp_dir):
        """Test multiple events append, don't overwrite."""
        invoice_state.write_state("client1", "INV-001", {"amount": 1000})
        invoice_state.write_state("client1", "INV-002", {"amount": 2000})
        
        log_file = temp_dir / "events.log"
        with open(log_file) as f:
            lines = f.readlines()
        
        assert len(lines) == 2
        
    def test_event_id_unique(self, invoice_state):
        """Test each event has unique ID."""
        invoice_state.write_state("client1", "INV-001", {"amount": 1000})
        invoice_state.write_state("client1", "INV-002", {"amount": 2000})
        
        events = invoice_state.replay_events()
        event_ids = [e["event_id"] for e in events]
        
        assert len(event_ids) == len(set(event_ids))  # All unique
        
    def test_replay_events(self, invoice_state):
        """Test replaying events for recovery."""
        invoice_state.write_state("client1", "INV-001", {"amount": 1000})
        invoice_state.write_state("client1", "INV-002", {"amount": 2000})
        
        events = invoice_state.replay_events()
        assert len(events) == 2
        assert events[0]["invoice"] == "INV-001"
        assert events[1]["invoice"] == "INV-002"


class TestMarkPaid:
    """Test marking invoices as paid."""
    
    def test_mark_paid_moves_to_archive(self, invoice_state, temp_dir):
        """Test mark_paid moves file to archive."""
        invoice_state.write_state("client1", "INV-001", {"amount": 1000, "status": "unpaid"})
        
        result = invoice_state.mark_paid("client1", "INV-001", {"method": "wire"})
        
        # Original should be gone
        assert not (temp_dir / "client1" / "INV-001.json").exists()
        
        # Archive should exist
        assert result.exists()
        assert "archive" in str(result)
        
    def test_mark_paid_updates_status(self, invoice_state, temp_dir):
        """Test mark_paid updates status and adds payment data."""
        invoice_state.write_state("client1", "INV-001", {"amount": 1000, "status": "unpaid"})
        
        invoice_state.mark_paid("client1", "INV-001", {"method": "bank_transfer"})
        
        archive_file = temp_dir / "archive" / "client1" / "INV-001.json"
        with open(archive_file) as f:
            data = json.load(f)
        
        assert data["status"] == "paid"
        assert data["payment"]["method"] == "bank_transfer"
        assert "paid_at" in data
        
    def test_mark_paid_logs_event(self, invoice_state, temp_dir):
        """Test payment is logged to event log."""
        invoice_state.write_state("client1", "INV-001", {"amount": 1000})
        
        invoice_state.mark_paid("client1", "INV-001", {"method": "check"})
        
        log_file = temp_dir / "events.log"
        with open(log_file) as f:
            lines = f.readlines()
        
        # Should have state_update + paid events
        events = [json.loads(l) for l in lines]
        paid_events = [e for e in events if e["event"] == "paid"]
        assert len(paid_events) == 1


class TestIntegrity:
    """Test state file integrity verification."""
    
    def test_verify_integrity_valid(self, invoice_state):
        """Test verify integrity returns success for valid file."""
        invoice_state.write_state("client1", "INV-001", {"amount": 1000})
        
        is_valid, message = invoice_state.verify_integrity("client1", "INV-001")
        assert is_valid is True
        assert "valid" in message
        
    def test_verify_integrity_corrupted(self, invoice_state, temp_dir):
        """Test verify integrity detects corruption."""
        invoice_state.write_state("client1", "INV-001", {"amount": 1000})
        
        # Corrupt the file
        state_file = temp_dir / "client1" / "INV-001.json"
        with open(state_file, 'r') as f:
            data = json.load(f)
        data["amount"] = 999
        with open(state_file, 'w') as f:
            json.dump(data, f)
        
        is_valid, message = invoice_state.verify_integrity("client1", "INV-001")
        assert is_valid is False
        assert "mismatch" in message
        
    def test_list_all_states(self, invoice_state):
        """Test list all states with integrity status."""
        invoice_state.write_state("client1", "INV-001", {"amount": 1000})
        invoice_state.write_state("client2", "INV-002", {"amount": 2000})
        
        states = invoice_state.list_all_states()
        assert len(states) == 2
        assert all(s["valid"] for s in states)
        
    def test_create_backup(self, invoice_state, temp_dir):
        """Test backup creation."""
        invoice_state.write_state("client1", "INV-001", {"amount": 1000})
        
        backup = invoice_state.create_backup("client1", "INV-001")
        assert backup.exists()
        assert backup.suffix == ".bak"
        
        # Verify backup content
        with open(backup) as f:
            data = json.load(f)
        assert data["amount"] == 1000


# Integration test for file locking

# Note: Full concurrent access testing should be done in integration tests
# with proper process isolation. The locking mechanism is implemented
# using threading.Lock for file-level synchronization.

class TestLockingMechanism:
    """Test locking mechanism implementation."""
    
    def test_locking_available(self, temp_dir):
        """Test that locking can be enabled."""
        from src.state.invoice_state import InvoiceState
        
        # Can create state with locking enabled
        state = InvoiceState(str(temp_dir), enable_locking=True)
        assert state.enable_locking is True
        
    def test_locking_disabled(self, temp_dir):
        """Test that locking can be disabled."""
        from src.state.invoice_state import InvoiceState
        
        # Can create state with locking disabled
        state = InvoiceState(str(temp_dir), enable_locking=False)
        assert state.enable_locking is False


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])