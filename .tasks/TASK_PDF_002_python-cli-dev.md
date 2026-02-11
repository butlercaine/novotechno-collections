# TASK: Atomic State File Writes & Ledger
**Task ID:** TASK_PDF_002
**Owner:** python-cli-dev-novotechno
**Type:** implementation
**Priority:** P0
**Status:** PENDING
**Created:** 2026-02-11 08:00 GMT-5

## Context
Implement atomic state file writes to prevent corruption during writes. Must survive crash/restart scenarios with checksums and append-only event logs.

## Requirements

### 1. Atomic State File Writer
**File:** `novotechno-collections/src/state/invoice_state.py`

**Implementation:**
```python
import os
import json
import hashlib
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Any
from contextlib import contextmanager

class InvoiceState:
    def __init__(self, state_dir: str):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
    
    @contextmanager
    def atomic_write(self, filepath: Path):
        """Write to .tmp file, then atomic replace"""
        tmp_path = filepath.with_suffix(filepath.suffix + ".tmp")
        try:
            # Write to tmp file
            with open(tmp_path, 'w') as f:
                yield f
            
            # Verify tmp file is complete
            tmp_path.chmod(0o600)  # Restrict permissions
            
            # Atomic replace
            shutil.move(str(tmp_path), str(filepath))
            
        except Exception as e:
            # Clean up tmp file on error
            if tmp_path.exists():
                tmp_path.unlink()
            raise
    
    def write_state(self, client: str, invoice: str, data: Dict):
        """Write invoice state with checksum"""
        state_file = self.state_dir / client / f"{invoice}.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        
        with self.atomic_write(state_file) as f:
            # Add checksum
            checksum = self._compute_checksum(data)
            state_data = {
                **data,
                "_checksum": checksum,
                "_updated_at": datetime.utcnow().isoformat()
            }
            json.dump(state_data, f, indent=2)
        
        # Append to event log
        self._log_event(client, invoice, "state_update", data)
        
        return state_file
    
    def read_state(self, client: str, invoice: str) -> Optional[Dict]:
        """Read invoice state, verify checksum"""
        state_file = self.state_dir / client / f"{invoice}.json"
        if not state_file.exists():
            return None
        
        with open(state_file) as f:
            data = json.load(f)
        
        # Verify checksum
        stored_checksum = data.pop("_checksum", None)
        if stored_checksum:
            computed = self._compute_checksum(data)
            if stored_checksum != computed:
                raise StateCorruptionError(f"Checksum mismatch for {invoice}")
        
        return data
    
    def mark_paid(self, client: str, invoice: str, payment_data: Dict):
        """Mark invoice as paid, move to archive"""
        state_file = self.state_dir / client / f"{invoice}.json"
        
        # Update state
        data = self.read_state(client, invoice)
        data["status"] = "paid"
        data["paid_at"] = datetime.utcnow().isoformat()
        data["payment"] = payment_data
        
        self.write_state(client, invoice, data)
        
        # Move to archive
        archive_dir = self.state_dir / "archive" / client
        archive_dir.mkdir(parents=True, exist_ok=True)
        
        with self.atomic_write(archive_dir / f"{invoice}.json") as f:
            json.dump(data, f, indent=2)
        
        # Remove original
        state_file.unlink()
        
        return archive_dir / f"{invoice}.json"
    
    def _compute_checksum(self, data: Dict) -> str:
        """Compute SHA-256 checksum of data"""
        content = json.dumps(data, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def _log_event(self, client: str, invoice: str, event_type: str, data: Any):
        """Append-only event log for audit trail"""
        log_file = self.state_dir / "events.log"
        with open(log_file, 'a') as f:
            entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "client": client,
                "invoice": invoice,
                "event": event_type,
                "data": data
            }
            f.write(json.dumps(entry) + "\n")

class StateCorruptionError(Exception):
    """Raised when state file checksum fails"""
    pass
```

### 2. QMD Ledger Implementation
**File:** `novotechno-collections/src/state/ledger.py`

**Implementation:**
```python
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional

class Ledger:
    def __init__(self, ledger_path: str):
        self.ledger_path = Path(ledger_path)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_ledger_exists()
    
    def _ensure_ledger_exists(self):
        """Create ledger file with sections if not exists"""
        if not self.ledger_path.exists():
            with open(self.ledger_path, 'w') as f:
                f.write("# Collections Ledger\n\n")
                f.write("## Unpaid\n\n")
                f.write("## Paid\n\n")
                f.write("## Escalated\n\n")
    
    def add_invoice(self, invoice_data: Dict):
        """Add invoice to unpaid section"""
        self._append_to_section("## Unpaid", f"- {invoice_data['invoice_number']}: ${invoice_data['amount']} ({invoice_data['client']})")
        
        # Log to internal state
        self._update_totals("unpaid", invoice_data['amount'])
    
    def mark_paid(self, invoice_number: str, amount: float, client: str):
        """Move invoice from unpaid to paid"""
        # Remove from unpaid (simplified - in production would use regex replace)
        # Add to paid
        self._append_to_section("## Paid", f"- {invoice_number}: ${amount} ({client}) - {datetime.now().isoformat()}")
        
        # Update totals
        self._update_totals("paid", amount)
        self._update_totals("unpaid", -amount)
    
    def escalate(self, invoice_number: str, amount: float, client: str, reason: str):
        """Move invoice to escalated section"""
        self._append_to_section("## Escalated", f"- {invoice_number}: ${amount} ({client}) - {reason}")
        
        # Update totals
        self._update_totals("escalated", amount)
    
    def get_summary(self) -> Dict:
        """Get ledger summary"""
        unpaid = self._sum_section("## Unpaid")
        paid = self._sum_section("## Paid")
        escalated = self._sum_section("## Escalated")
        
        return {
            "unpaid_total": unpaid,
            "paid_total": paid,
            "escalated_total": escalated,
            "total_invoices": unpaid + paid + escalated
        }
    
    def reconcile(self, state_dir: str) -> Tuple[bool, str]:
        """Reconcile ledger with state files"""
        import json
        from pathlib import Path
        
        state_path = Path(state_dir)
        
        # Sum state files
        state_total = 0
        for state_file in state_path.rglob("*.json"):
            with open(state_file) as f:
                data = json.load(f)
                if data.get("status") == "unpaid":
                    state_total += data.get("amount", 0)
        
        # Compare with ledger
        summary = self.get_summary()
        ledger_total = summary["unpaid_total"]
        
        if abs(state_total - ledger_total) < 0.01:
            return True, f"Reconciliation passed: ${state_total:.2f} matches"
        else:
            return False, f"Reconciliation failed: state=${state_total:.2f}, ledger=${ledger_total:.2f}"
    
    def _append_to_section(self, section_header: str, entry: str):
        """Append entry to ledger section"""
        with open(self.ledger_path) as f:
            content = f.read()
        
        # Find section and append
        lines = content.split("\n")
        idx = lines.index(section_header)
        lines.insert(idx + 2, entry)
        
        with open(self.ledger_path, 'w') as f:
            f.write("\n".join(lines))
    
    def _sum_section(self, section_header: str) -> float:
        """Sum all amounts in a section"""
        total = 0.0
        pattern = r"\$([0-9,]+\.?\d*)"
        
        with open(self.ledger_path) as f:
            content = f.read()
        
        # Simplified - in production would parse section more carefully
        matches = re.findall(pattern, content)
        for match in matches:
            total += float(match.replace(",", ""))
        
        return total
    
    def _update_totals(self, section: str, amount: float):
        """Update running totals"""
        # Implementation for maintaining running totals
        pass
```

### 3. Unit Tests
**File:** `novotechno-collections/tests/test_atomic_writes.py`

```python
import pytest
import os
import tempfile
from src.state.invoice_state import InvoiceState, StateCorruptionError
from src.state.ledger import Ledger

@pytest.fixture
def state_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir

@pytest.fixture
def invoice_state(state_dir):
    return InvoiceState(state_dir)

def test_atomic_write_creates_file(invoice_state, state_dir):
    """Test atomic write creates file"""
    invoice_state.write_state("client1", "INV-001", {"amount": 1000})
    
    state_file = f"{state_dir}/client1/INV-001.json"
    assert os.path.exists(state_file)

def test_checksum_verification(invoice_state):
    """Test checksum is added and verified"""
    data = {"amount": 1000, "client": "ACME"}
    invoice_state.write_state("client1", "INV-001", data)
    
    read_data = invoice_state.read_state("client1", "INV-001")
    assert read_data["amount"] == 1000
    assert "_checksum" in read_data

def test_corruption_detection(invoice_state, state_dir):
    """Test checksum mismatch raises error"""
    invoice_state.write_state("client1", "INV-001", {"amount": 1000})
    
    # Corrupt the file
    with open(f"{state_dir}/client1/INV-001.json", 'w') as f:
        f.write('{"amount": 2000, "_checksum": "fake"}')
    
    with pytest.raises(StateCorruptionError):
        invoice_state.read_state("client1", "INV-001")

def test_mark_paid_moves_to_archive(invoice_state, state_dir):
    """Test mark_paid moves file to archive"""
    invoice_state.write_state("client1", "INV-001", {"amount": 1000, "status": "unpaid"})
    
    archive_file = invoice_state.mark_paid("client1", "INV-001", {"method": "bank_transfer"})
    
    assert os.path.exists(archive_file)
    assert not os.path.exists(f"{state_dir}/client1/INV-001.json")
    
    # Verify archived state
    with open(archive_file) as f:
        data = json.load(f)
    assert data["status"] == "paid"
    assert data["paid_at"] is not None

def test_event_log_append_only(invoice_state, state_dir):
    """Test events are appended to log"""
    invoice_state.write_state("client1", "INV-001", {"amount": 1000})
    invoice_state.write_state("client1", "INV-002", {"amount": 2000})
    
    with open(f"{state_dir}/events.log") as f:
        lines = f.readlines()
    
    assert len(lines) == 2
    assert "INV-001" in lines[0]
    assert "INV-002" in lines[1]
```

## Dependencies
- Standard library only (json, pathlib, hashlib, shutil)

## Output Files
- `novotechno-collections/src/state/__init__.py`
- `novotechno-collections/src/state/invoice_state.py` (250 lines)
- `novotechno-collections/src/state/ledger.py` (200 lines)
- `novotechno-collections/tests/test_atomic_writes.py` (100 lines)
- `novotechno-collections/tests/test_ledger.py` (80 lines)

## Definition of Done
- [ ] Atomic write prevents partial files
- [ ] Checksum verification works
- [ ] Event log append-only
- [ ] Ledger reconciliation passes
- [ ] Kill -9 test: state file intact
- [ ] RESPONSE file written

## Success Criteria (from PROJECT_SCOPING)
- [ ] No partial writes after crash (C-005)
- [ ] State file survives kill -9 test
- [ ] Checksum comments added
- [ ] Append-only event log functional

## Dependencies
- TASK_PDF_001 (must complete first)

## Next Task
TASK_CLI_001 (collections-emailer) — depends on this task
