"""
QMD Ledger Implementation
Project: PROJ-2026-0210-novotechno-collections
"""

import re
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any


class LedgerError(Exception):
    """Raised for ledger-related errors."""
    pass


class LedgerParseError(Exception):
    """Raised when ledger parsing fails."""
    pass


class Ledger:
    """
    QMD (Quick Markdown) Ledger for tracking invoice status.
    
    Features:
    - Human-readable markdown format
    - Sections: Unpaid, Paid, Escalated
    - Running totals maintained
    - Automatic reconciliation with state files
    - Transaction history tracking
    """
    
    def __init__(self, ledger_path: str, create_if_missing: bool = True):
        """
        Initialize ledger.
        
        Args:
            ledger_path: Path to ledger file
            create_if_missing: Create if doesn't exist
        """
        self.ledger_path = Path(ledger_path)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        
        if create_if_missing and not self.ledger_path.exists():
            self._create_initial()
            
        self._totals = {"unpaid": 0.0, "paid": 0.0, "escalated": 0.0}
        self._load_totals()
        
    def _create_initial(self):
        """Create initial ledger structure."""
        content = """# Collections Ledger

## Unpaid

## Paid

## Escalated

## Summary
- **Unpaid Total:** $0.00
- **Paid Total:** $0.00
- **Escalated Total:** $0.00
- **Grand Total:** $0.00
"""
        with open(self.ledger_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
    def _load_totals(self):
        """Load running totals from ledger."""
        try:
            if not self.ledger_path.exists():
                return
                
            content = self.ledger_path.read_text(encoding='utf-8')
            
            # Parse summary section
            summary_match = re.search(r'## Summary\s+(.*?)(?=\n##|$)', content, re.DOTALL)
            if summary_match:
                summary = summary_match.group(1)
                
                # Extract totals
                unpaid_match = re.search(r'Unpaid Total.*?\$([\d,]+\.?\d*)', summary)
                if unpaid_match:
                    self._totals["unpaid"] = float(unpaid_match.group(1).replace(',', ''))
                    
                paid_match = re.search(r'Paid Total.*?\$([\d,]+\.?\d*)', summary)
                if paid_match:
                    self._totals["paid"] = float(paid_match.group(1).replace(',', ''))
                    
                escalated_match = re.search(r'Escalated Total.*?\$([\d,]+\.?\d*)', summary)
                if escalated_match:
                    self._totals["escalated"] = float(escalated_match.group(1).replace(',', ''))
                    
        except Exception as e:
            raise LedgerParseError(f"Failed to parse ledger: {e}")
            
    def add_invoice(self, invoice_data: Dict[str, Any]) -> bool:
        """
        Add invoice to unpaid section.
        
        Args:
            invoice_data: Dictionary with invoice info
            
        Returns:
            True if successfully added
            
        Raises:
            LedgerError: If invoice already exists
        """
        required = ['invoice_number', 'amount', 'client_name']
        if not all(k in invoice_data for k in required):
            raise LedgerError(f"Missing required fields: {required}")
            
        invoice_num = invoice_data['invoice_number']
        amount = invoice_data['amount']
        client = invoice_data['client_name']
        due_date = invoice_data.get('due_date', '')
        
        # Check if already exists anywhere in ledger
        if self._invoice_exists(invoice_num):
            raise LedgerError(f"Invoice {invoice_num} already exists in ledger")
            
        # Build entry
        entry = f"- `{invoice_num}` | ${amount:,.2f} | {client}"
        if due_date:
            entry += f" | Due: {due_date}"
        entry += " | Status: unpaid"
        
        # Add to unpaid section
        self._append_to_section("## Unpaid", entry)
        
        # Update totals
        self._update_totals("unpaid", amount)
        
        return True
        
    def mark_paid(self, invoice_number: str, amount: float, 
                  payment_date: Optional[str] = None,
                  payment_method: Optional[str] = None) -> bool:
        """
        Move invoice from unpaid to paid.
        
        Args:
            invoice_number: Invoice identifier
            amount: Payment amount
            payment_date: Date of payment
            payment_method: Payment method used
            
        Returns:
            True if successfully marked paid
            
        Raises:
            LedgerError: If invoice not found or already paid
        """
        if not self._remove_from_unpaid(invoice_number):
            raise LedgerError(f"Invoice {invoice_number} not found in unpaid section")
            
        # Build paid entry
        entry = f"- `{invoice_number}` | ${amount:,.2f}"
        if payment_date:
            entry += f" | Paid: {payment_date}"
        if payment_method:
            entry += f" | Method: {payment_method}"
        entry += " | Status: paid"
        
        # Add to paid section
        self._append_to_section("## Paid", entry)
        
        # Update totals
        self._update_totals("unpaid", -amount)
        self._update_totals("paid", amount)
        
        return True
        
    def escalate(self, invoice_number: str, amount: float, 
                 reason: str, escalated_date: Optional[str] = None) -> bool:
        """
        Move invoice to escalated section.
        
        Args:
            invoice_number: Invoice identifier
            amount: Invoice amount
            reason: Escalation reason
            escalated_date: Date escalated
            
        Returns:
            True if successfully escalated
        """
        if not self._remove_from_unpaid(invoice_number):
            raise LedgerError(f"Invoice {invoice_number} not found in unpaid section")
            
        # Build escalated entry
        entry = f"- `{invoice_number}` | ${amount:,.2f} | {reason}"
        if escalated_date:
            entry += f" | Escalated: {escalated_date}"
        entry += " | Status: escalated"
        
        # Add to escalated section
        self._append_to_section("## Escalated", entry)
        
        # Update totals
        self._update_totals("unpaid", -amount)
        self._update_totals("escalated", amount)
        
        return True
        
    def reconcile(self, state_dir: str, auto_fix: bool = False) -> Dict[str, Any]:
        """
        Reconcile ledger with state files.
        
        Args:
            state_dir: Directory containing state files
            auto_fix: Automatically fix discrepancies
            
        Returns:
            Dict with reconciliation results
        """
        from pathlib import Path
        
        state_path = Path(state_dir)
        if not state_path.exists():
            raise LedgerError(f"State directory not found: {state_dir}")
            
        # Sum unpaid invoices from state files
        state_total = 0.0
        state_count = 0
        
        unpaid_files = list(state_path.rglob("*.json"))
        
        for state_file in unpaid_files:
            if state_file.parent.name == "archive":
                continue
                
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                if data.get("status") in ["unpaid", "pending"]:
                    amount = data.get("amount", 0)
                    if isinstance(amount, (int, float)):
                        state_total += amount
                        state_count += 1
            except Exception as e:
                if not auto_fix:
                    raise LedgerError(f"Error reading {state_file}: {e}")
                    
        # Compare with ledger
        ledger_summary = self.get_summary()
        ledger_total = ledger_summary["unpaid_total"]
        
        discrepancy = abs(state_total - ledger_total)
        passed = discrepancy < 0.01
        
        result = {
            "passed": passed,
            "state_total": state_total,
            "ledger_total": ledger_total,
            "discrepancy": discrepancy,
            "state_count": state_count,
            "auto_fixed": False
        }
        
        if auto_fix and not passed:
            # Remove invalid entries from ledger
            self._fix_discrepancies(unpaid_files)
            result["auto_fixed"] = True
            
        return result
        
    def get_summary(self) -> Dict[str, Any]:
        """Get ledger summary with totals."""
        return {
            "unpaid_total": self._totals["unpaid"],
            "paid_total": self._totals["paid"],
            "escalated_total": self._totals["escalated"],
            "grand_total": sum(self._totals.values())
        }
        
    def get_all_unpaid(self) -> List[Dict[str, Any]]:
        """
        Get all unpaid invoices from the ledger.
        
        Returns:
            List of unpaid invoice dictionaries
        """
        unpaid_invoices = []
        
        try:
            content = self.ledger_path.read_text(encoding='utf-8')
            
            # Find unpaid section
            unpaid_match = re.search(r'## Unpaid\s+(.+?)(?=\n##|\Z)', content, re.DOTALL)
            if not unpaid_match:
                return unpaid_invoices
                
            unpaid_section = unpaid_match.group(1)
            
            # Parse each line in unpaid section
            for line in unpaid_section.split('\n'):
                line = line.strip()
                if not line or not line.startswith('- '):
                    continue
                    
                # Parse invoice entry
                # Format: `- `INV-001` | $1,000.00 | Client Name | Due: 2023-12-31 | Status: unpaid`
                match = re.search(r'- `([^`]+)` \| \$([\d,]+\.?\d*) \| ([^|]+)(?: \| Due: ([^|]+))?', line)
                if match:
                    invoice_number = match.group(1)
                    amount = float(match.group(2).replace(',', ''))
                    client_name = match.group(3).strip()
                    due_date = match.group(4) or datetime.utcnow().isoformat()
                    
                    unpaid_invoices.append({
                        "invoice_number": invoice_number,
                        "amount": amount,
                        "client_name": client_name,
                        "due_date": due_date,
                        "email": "unknown@example.com"  # Default if not specified
                    })
                    
        except Exception as e:
            # Log error but return empty list rather than crashing
            print(f"Warning: Failed to parse unpaid invoices: {e}")
            
        return unpaid_invoices
        
    def export_json(self, output_path: str) -> Path:
        """Export ledger to JSON format."""
        content = self.ledger_path.read_text(encoding='utf-8')
        
        # Parse sections
        sections = {}
        current_section = None
        
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith("## "):
                current_section = line[3:].lower()
                sections[current_section] = []
            elif line.startswith("- ") and current_section:
                sections[current_section].append(line[2:])
                
        summary = self.get_summary()
        export = {
            "export_date": datetime.utcnow().isoformat(),
            "summary": summary,
            "sections": sections
        }
        
        output = Path(output_path)
        with open(output, 'w', encoding='utf-8') as f:
            json.dump(export, f, indent=2)
            
        return output
        
    def _invoice_exists(self, invoice_number: str) -> bool:
        """Check if invoice exists anywhere in ledger."""
        content = self.ledger_path.read_text(encoding='utf-8')
        return f"`{invoice_number}`" in content
        
    def _append_to_section(self, section_header: str, entry: str):
        """Append entry to specific section."""
        with open(self.ledger_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Find section and append 
        lines = content.split('\n')
        section_idx = None
        next_section_idx = None
        
        for i, line in enumerate(lines):
            if line.strip() == section_header:
                section_idx = i
            elif section_idx is not None and line.startswith("## "):
                next_section_idx = i
                break
                
        if section_idx is None:
            raise LedgerError(f"Section {section_header} not found")
            
        # Insert after section header (skip one line for content)
        insert_at = section_idx + 2 if next_section_idx is None else min(section_idx + 2, next_section_idx)
        lines.insert(insert_at, entry)
        
        with open(self.ledger_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
            
    def _remove_from_unpaid(self, invoice_number: str) -> bool:
        """Remove invoice from unpaid section."""
        with open(self.ledger_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        lines = content.split('\n')
        unpaid_start = None
        unpaid_end = None
        
        for i, line in enumerate(lines):
            if line.strip() == "## Unpaid":
                unpaid_start = i
            elif unpaid_start is not None and line.startswith("## "):
                unpaid_end = i
                break
                
        if unpaid_start is None:
            return False
            
        # Find and remove the invoice
        found = False
        unpaid_end = unpaid_end if unpaid_end else len(lines)
        
        for i in range(unpaid_start, unpaid_end):
            if f"`{invoice_number}`" in lines[i]:
                lines.pop(i)
                found = True
                break
                
        if found:
            with open(self.ledger_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
                
        return found
        
    def _update_totals(self, section: str, amount: float):
        """Update running totals in summary section."""
        section = section.lower()
        if section not in self._totals:
            return
            
        self._totals[section] += amount
        
        # Update summary section
        with open(self.ledger_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Update individual total
        old_total = f"**{section.title()} Total:** ${self._totals[section] - amount:.2f}"
        new_total = f"**{section.title()} Total:** ${self._totals[section]:.2f}"
        content = content.replace(old_total, new_total)
        
        # Update grand total
        old_grand = f"**Grand Total:** ${sum([self._totals[s] for s in self._totals]) - amount:.2f}"
        new_grand = f"**Grand Total:** ${sum(self._totals.values()):.2f}"
        content = content.replace(old_grand, new_grand)
        
        with open(self.ledger_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
    def _fix_discrepancies(self, unpaid_files: List[Path]):
        """Fix discrepancies between ledger and state files."""
        # Remove entries that don't have corresponding state files
        # This is a simplified implementation
        content = self.ledger_path.read_text(encoding='utf-8')
        
        # Mark for removal (simplified)
        lines = content.split('\n')
        cleaned = []
        skip_next = False
        
        for line in lines:
            if '## Unpaid' in line:
                cleaned.append(line)
                cleaned.append('')  # Empty line after header
                # Re-add valid unpaid invoices from state files
                for state_file in unpaid_files:
                    try:
                        data = json.loads(state_file.read_text())
                        invoice_num = data.get('invoice_number', state_file.stem)
                        amount = data.get('amount', 0)
                        client = data.get('client_name', 'Unknown')
                        entry = f"- `{invoice_num}` | ${amount:.2f} | {client} | Status: unpaid"
                        cleaned.append(entry)
                    except:
                        continue
                skip_next = True
            elif skip_next and line.strip() == '':
                skip_next = False
                continue
            elif not skip_next:
                cleaned.append(line)
                
        self.ledger_path.write_text('\n'.join(cleaned), encoding='utf-8')