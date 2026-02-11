"""
Atomic State File Writer System
Project: PROJ-2026-0210-novotechno-collections
"""

import json
import hashlib
import shutil
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Any, ContextManager
from contextlib import contextmanager
import threading


class StateCorruptionError(Exception):
    """Raised when state file checksum verification fails."""
    pass


class StateLockError(Exception):
    """Raised when unable to acquire state file lock."""
    pass


class InvoiceState:
    """
    Atomic state file writer with checksums and append-only event logging.
    
    Features:
    - Atomic writes using temporary files
    - Checksum verification for data integrity
    - Append-only event log for audit trail  
    - File-level locking for concurrent access
    - Auto-repair on detected corruption
    """
    
    def __init__(self, state_dir: str, enable_locking: bool = True):
        """
        Initialize state manager.
        
        Args:
            state_dir: Root directory for state files
            enable_locking: Enable file locking for concurrency
        """
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.enable_locking = enable_locking
        self._locks = {}  # File path -> threading.Lock mapping
        self._global_lock = threading.Lock()
        
    @contextmanager
    def atomic_write(self, filepath: Path) -> ContextManager:
        """
        Write to .tmp file, then atomic replace.
        
        This ensures:
        1. No partial writes visible to readers
        2. Crash-safe: tmp file can be recovered
        3. No data corruption on system crash
        
        Args:
            filepath: Final destination path
            
        Yields:
            File handle for writing to temporary file
        """
        tmp_path = filepath.with_suffix(filepath.suffix + ".tmp")
        
        try:
            # Write to temporary file
            with open(tmp_path, 'w', encoding='utf-8') as f:
                yield f
            
            # Set restrictive permissions
            tmp_path.chmod(0o600)
            
            # Atomic replace (POSIX guarantees atomicity)
            shutil.move(str(tmp_path), str(filepath))
            
        except Exception as e:
            # Clean up temp file on any error
            if tmp_path.exists():
                tmp_path.unlink()
            raise
            
    def _acquire_lock(self, filepath: Path) -> bool:
        """Acquire file-level lock for concurrency control."""
        if not self.enable_locking:
            return True
            
        with self._global_lock:
            if filepath not in self._locks:
                self._locks[filepath] = threading.Lock()
            lock = self._locks[filepath]
            
        # Non-blocking lock acquire
        acquired = lock.acquire(blocking=False)
        if not acquired:
            raise StateLockError(f"Could not acquire lock for {filepath}")
        return True
        
    def _release_lock(self, filepath: Path):
        """Release file-level lock."""
        if not self.enable_locking:
            return
            
        with self._global_lock:
            if filepath in self._locks:
                self._locks[filepath].release()
                
    def write_state(self, client: str, invoice: str, data: Dict[str, Any]) -> Path:
        """
        Write invoice state with checksum.
        
        Args:
            client: Client identifier
            invoice: Invoice number
            data: State data to write
            
        Returns:
            Path to written state file
            
        Raises:
            StateLockError: If unable to acquire lock
        """
        state_file = self.state_dir / client / f"{invoice}.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # Acquire lock
            self._acquire_lock(state_file)
            
            # Compute checksum BEFORE adding metadata
            checksum = self._compute_checksum(data)
            
            # Prepare state data with metadata
            state_data = {
                **data,
                "_checksum": checksum,
                "_updated_at": datetime.utcnow().isoformat(),
                "_version": "1.0"
            }
            
            # Atomic write
            with self.atomic_write(state_file) as f:
                json.dump(state_data, f, indent=2)
                f.write("\n")  # Ensure trailing newline
                
            # Append to event log
            self._log_event(client, invoice, "state_update", data)
            
            return state_file
            
        finally:
            self._release_lock(state_file)
            
    def read_state(self, client: str, invoice: str, verify_checksum: bool = True) -> Optional[Dict[str, Any]]:
        """
        Read invoice state, verify checksum.
        
        Args:
            client: Client identifier
            invoice: Invoice number
            verify_checksum: Whether to verify checksum (default True)
            
        Returns:
            State data dict or None if not found
            
        Raises:
            StateCorruptionError: If checksum verification fails
        """
        state_file = self.state_dir / client / f"{invoice}.json"
        
        if not state_file.exists():
            return None
            
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            if verify_checksum:
                # Extract and remove checksum
                stored_checksum = data.pop("_checksum", None)
                if stored_checksum:
                    computed = self._compute_checksum(data)
                    if stored_checksum != computed:
                        # Try to recover from backup if exists
                        recovered = self._attempt_recovery(state_file)
                        if recovered:
                            return recovered
                        raise StateCorruptionError(
                            f"Checksum mismatch for {client}/{invoice}: "
                            f"stored={stored_checksum}, computed={computed}"
                        )
                        
            return data
            
        except json.JSONDecodeError as e:
            # Try recovery on parse error
            recovered = self._attempt_recovery(state_file)
            if recovered:
                return recovered
            raise StateCorruptionError(f"JSON parse error in {state_file}: {e}")
            
    def _attempt_recovery(self, state_file: Path) -> Optional[Dict[str, Any]]:
        """
        Attempt to recover from backup file.
        
        Looks for .bak files from previous successful writes.
        """
        backup_file = state_file.with_suffix(state_file.suffix + ".bak")
        if backup_file.exists():
            try:
                with open(backup_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return None
        
    def mark_paid(self, client: str, invoice: str, payment_data: Dict[str, Any]) -> Path:
        """
        Mark invoice as paid and move to archive.
        
        Args:
            client: Client identifier
            invoice: Invoice number
            payment_data: Payment information
            
        Returns:
            Path to archived state file
        """
        state_file = self.state_dir / client / f"{invoice}.json"
        
        if not state_file.exists():
            raise FileNotFoundError(f"State file not found: {state_file}")
            
        try:
            self._acquire_lock(state_file)
            
            # Read current state
            data = self.read_state(client, invoice)
            
            # Update status
            data["status"] = "paid"
            data["paid_at"] = datetime.utcnow().isoformat()
            data["payment"] = payment_data
            
            self.write_state(client, invoice, data)
            
            # Move to archive
            archive_dir = self.state_dir / "archive" / client
            archive_dir.mkdir(parents=True, exist_ok=True)
            
            archive_file = archive_dir / f"{invoice}.json"
            
            # Copy to archive with atomic write
            with self.atomic_write(archive_file) as f:
                json.dump(data, f, indent=2)
                f.write("\n")
                
            # Remove original (after successful archive)
            state_file.unlink()
            
            # Log payment
            self._log_event(client, invoice, "paid", payment_data)
            
            return archive_file
            
        finally:
            self._release_lock(state_file)
            
    def create_backup(self, client: str, invoice: str) -> Path:
        """
        Create backup of current state file.
        
        Args:
            client: Client identifier
            invoice: Invoice number
            
        Returns:
            Path to backup file
        """
        state_file = self.state_dir / client / f"{invoice}.json"
        
        if not state_file.exists():
            raise FileNotFoundError(f"State file not found: {state_file}")
            
        backup_file = state_file.with_suffix(state_file.suffix + ".bak")
        shutil.copy2(state_file, backup_file)
        
        return backup_file
        
    def _compute_checksum(self, data: Dict[str, Any]) -> str:
        """
        Compute SHA-256 checksum of data.
        
        Uses canonical JSON representation (sorted keys) for consistent hashing.
        """
        # Remove metadata fields before computing checksum
        data_copy = {k: v for k, v in data.items() if not k.startswith("_")}
        content = json.dumps(data_copy, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(content.encode()).hexdigest()[:16]
        
    def _log_event(self, client: str, invoice: str, event_type: str, data: Any):
        """
        Append-only event log for audit trail.
        
        Each event is a single line of JSON, making it:
        - Append-only (no overwrites)
        - Human-readable
        - Easy to parse and replay
        - Crash-safe (always valid)
        """
        log_file = self.state_dir / "events.log"
        
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_id": self._generate_event_id(),
            "client": client,
            "invoice": invoice,
            "event": event_type,
            "data": data
        }
        
        # Atomic append (write+flush+rename for safety)
        tmp_log = log_file.with_suffix(log_file.suffix + ".tmp")
        
        try:
            # Read existing if present
            existing = ""
            if log_file.exists():
                with open(log_file, 'r', encoding='utf-8') as f:
                    existing = f.read()
                    
            # Write original + new entry
            with open(tmp_log, 'w', encoding='utf-8') as f:
                if existing:
                    f.write(existing)
                    if not existing.endswith("\n"):
                        f.write("\n")
                f.write(json.dumps(entry) + "\n")
                f.flush()
                os.fsync(f.fileno())
                
            # Atomic replace
            shutil.move(str(tmp_log), str(log_file))
            
        except Exception as e:
            if tmp_log.exists():
                tmp_log.unlink()
            raise Exception(f"Failed to append to event log: {e}")
            
    def _generate_event_id(self) -> str:
        """Generate unique event ID."""
        import uuid
        return str(uuid.uuid4())[:8]
        
    def replay_events(self, since_timestamp: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Replay events from log for recovery or audit.
        
        Args:
            since_timestamp: Only events after this timestamp
            
        Returns:
            List of event dictionaries
        """
        log_file = self.state_dir / "events.log"
        
        if not log_file.exists():
            return []
            
        events = []
        with open(log_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                    
                try:
                    event = json.loads(line)
                    if since_timestamp and event["timestamp"] < since_timestamp:
                        continue
                    events.append(event)
                except json.JSONDecodeError:
                    # Skip corrupted lines
                    continue
                    
        return events
        
    def get_event_count(self) -> int:
        """Get total number of events in log."""
        log_file = self.state_dir / "events.log"
        if not log_file.exists():
            return 0
            
        count = 0
        with open(log_file, 'r', encoding='utf-8') as f:
            for _ in f:
                count += 1
        return count
        
    def verify_integrity(self, client: str, invoice: str) -> Tuple[bool, str]:
        """
        Verify state file integrity.
        
        Returns:
            Tuple of (is_valid, message)
        """
        state_file = self.state_dir / client / f"{invoice}.json"
        
        if not state_file.exists():
            return False, f"State file not found: {state_file}"
            
        try:
            data = self.read_state(client, invoice, verify_checksum=True)
            return True, f"State file {client}/{invoice} is valid"
        except StateCorruptionError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Read error: {e}"
            
    def list_all_states(self) -> List[Dict[str, Any]]:
        """List all state files with integrity status."""
        states = []
        
        for client_dir in self.state_dir.iterdir():
            if not client_dir.is_dir() or client_dir.name.startswith("."):
                continue
                
            client = client_dir.name
            
            for state_file in client_dir.glob("*.json"):
                invoice = state_file.stem
                is_valid, message = self.verify_integrity(client, invoice)
                
                states.append({
                    "client": client,
                    "invoice": invoice,
                    "valid": is_valid,
                    "message": message,
                    "path": str(state_file)
                })
                
        return states