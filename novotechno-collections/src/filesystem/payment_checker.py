from typing import Dict, Optional
from pathlib import Path
import re
from decimal import Decimal
import logging

class PaymentConfidenceChecker:
    """Check if payment file matches an invoice"""
    
    def __init__(self, state_manager):
        self.state = state_manager
        self.logger = logging.getLogger(__name__)
    
    def __call__(self, payment_file: str) -> Dict:
        """Check payment against unpaid invoices"""
        payment_data = self._extract_payment_data(payment_file)
        
        # Find matching invoice
        matching_invoice = self._find_matching_invoice(
            amount=payment_data.get("amount"),
            client=payment_data.get("client"),
            invoice_number=payment_data.get("invoice_number")
        )
        
        if matching_invoice:
            # Verify amount matches
            amount_match = self._verify_amount(
                payment_data.get("amount"),
                matching_invoice["amount"]
            )
            
            return {
                "matches_invoice": True,
                "client": matching_invoice["client"],
                "invoice_number": matching_invoice["invoice_number"],
                "confidence": amount_match,
                "amount": payment_data.get("amount"),
                "method": payment_data.get("method"),
                "source_file": payment_file
            }
        
        return {
            "matches_invoice": False,
            "source_file": payment_file
        }
    
    def _extract_payment_data(self, filepath: str) -> Dict:
        """Extract payment info from file"""
        data = {
            "amount": None,
            "client": None,
            "invoice_number": None,
            "method": "unknown"
        }
        
        filepath_lower = filepath.lower()
        
        # Extract from filename
        if "bancolombia" in filepath_lower:
            data["method"] = "bancolombia"
        elif "davivienda" in filepath_lower:
            data["method"] = "davivienda"
        elif "transfer" in filepath_lower:
            data["method"] = "transfer"
        elif "pago" in filepath_lower:
            data["method"] = "pago"
        elif "payment" in filepath_lower:
            data["method"] = "payment"
        
        # Extract amount from filename pattern
        # Match formats like: $123.45, 1,234.56, 12345.67
        amount_patterns = [
            r"[\$]?([0-9,]+\.\d{2})",  # With decimal and cents
            r"[\$]?([0-9,]+)"           # Without decimal
        ]
        
        for pattern in amount_patterns:
            amount_match = re.search(pattern, Path(filepath).name)
            if amount_match:
                try:
                    amount_str = amount_match.group(1).replace(",", "")
                    data["amount"] = float(amount_str)
                    break
                except ValueError:
                    continue
        
        # Extract invoice number - look for patterns like:
        # factura-12345, invoice_ABC123, pagare-XYZ-001
        invoice_patterns = [
            r"(?:factura|invoice|pagare|inv)[\s_-]*([A-Z0-9-]+)",
            r"([A-Z]{2,3}[0-9]{3,6})"  # ABC123, INV456789
        ]
        
        for pattern in invoice_patterns:
            invoice_match = re.search(pattern, Path(filepath).name, re.IGNORECASE)
            if invoice_match:
                data["invoice_number"] = invoice_match.group(1)
                break
        
        # Try to extract client from path structure
        # Common pattern: /Clients/{client}/payments/...
        path_parts = Path(filepath).parts
        for i, part in enumerate(path_parts):
            if part.lower() in ["clients", "clientes"] and i + 1 < len(path_parts):
                data["client"] = path_parts[i + 1]
                break
        
        self.logger.debug(f"Extracted payment data: {data}")
        return data
    
    def _find_matching_invoice(self, amount: float, client: str = None, 
                               invoice_number: str = None) -> Optional[Dict]:
        """Find matching unpaid invoice"""
        try:
            unpaid = self.state.get_all_unpaid()
            
            for invoice in unpaid:
                # Match by invoice number first (highest confidence)
                if invoice_number and invoice.get("invoice_number") == invoice_number:
                    self.logger.info(f"Matched by invoice number: {invoice_number}")
                    return invoice
                
                # Match by amount (within 5% tolerance) if no invoice number
                if amount and client and invoice.get("client") == client:
                    try:
                        invoice_amount = float(invoice["amount"])
                        payment_amount = float(amount)
                        
                        # Calculate difference percentage
                        if invoice_amount > 0:
                            diff_percent = abs(invoice_amount - payment_amount) / invoice_amount
                            if diff_percent <= 0.05:  # 5% tolerance
                                self.logger.info(f"Matched by amount: {payment_amount} ≈ {invoice_amount}")
                                return invoice
                    except (ValueError, TypeError) as e:
                        self.logger.warning(f"Error comparing amounts: {e}")
                        continue
            
            self.logger.info(f"No matching invoice found for amount={amount}, client={client}, invoice_number={invoice_number}")
            return None
        except Exception as e:
            self.logger.error(f"Error finding matching invoice: {e}")
            return None
    
    def _verify_amount(self, payment_amount: float, invoice_amount: float) -> float:
        """Calculate confidence based on amount match"""
        try:
            if payment_amount is None or invoice_amount is None:
                return 0.0
            
            payment_amount = float(payment_amount)
            invoice_amount = float(invoice_amount)
            
            if abs(payment_amount - invoice_amount) < 0.01:  # Exact match
                return 1.0
            elif payment_amount < invoice_amount:
                # Partial payment
                return 0.95
            elif payment_amount > invoice_amount:
                # Overpayment
                return 0.90
            return 0.0
        except (ValueError, TypeError) as e:
            self.logger.error(f"Error verifying amount: {e}")
            return 0.0