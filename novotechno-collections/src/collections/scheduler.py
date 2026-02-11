"""Collection scheduler for sending automated reminder emails."""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import json
from pathlib import Path


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded."""
    pass


def get_current_time():
    """Get current time - can be mocked for testing."""
    return datetime.now()


class CollectionScheduler:
    """Schedule and send collection reminder emails."""
    
    REMINDER_RULES = {
        "reminder_1": {"days_before_due": 3, "template": "reminder_3d"},
        "reminder_2": {"days_before_due": 0, "template": "reminder_due"},
        "overdue_1": {"days_after_due": 5, "template": "overdue_5d"},
        "overdue_2": {"days_after_due": 7, "template": "overdue_7d"},
        "final_notice": {"days_after_due": 10, "template": "final_notice"},
        "escalation": {"days_after_due": 14, "template": "escalation"},
    }
    
    def __init__(self, email_sender, state_manager, time_provider=None):
        """Initialize scheduler with email sender and state manager.
        
        Args:
            email_sender: Email sender instance
            state_manager: State manager instance
            time_provider: Callable that returns current time (for testing)
        """
        self.sender = email_sender
        self.state = state_manager
        self._time_provider = time_provider or get_current_time
    
    def _now(self):
        """Get current time using provider."""
        return self._time_provider()
    
    def get_due_reminders(self) -> List[Dict[str, Any]]:
        """Get list of invoices needing reminders today.
        
        Returns:
            List of reminder dictionaries
        """
        reminders = []
        now = self._now()
        
        for invoice in self.state.get_all_unpaid():
            due_date = datetime.fromisoformat(invoice["due_date"])
            days_until_due = (due_date - now).days
            
            for rule_name, rule in self.REMINDER_RULES.items():
                # Check for reminders before due date
                if "days_before_due" in rule and days_until_due == rule["days_before_due"]:
                    reminders.append({
                        "invoice": invoice,
                        "rule": rule_name,
                        "template": rule["template"],
                        "days_until_due": days_until_due
                    })
                # Check for reminders after due date (overdue)
                elif "days_after_due" in rule and days_until_due == -rule["days_after_due"]:
                    reminders.append({
                        "invoice": invoice,
                        "rule": rule_name,
                        "template": rule["template"],
                        "days_overdue": abs(days_until_due)
                    })
        
        return reminders
    
    def send_reminders(self, batch_size: int = 20) -> Dict[str, int]:
        """Send reminders, respecting rate limits.
        
        Args:
            batch_size: Maximum number of emails to send per batch
            
        Returns:
            Dictionary with sent, failed, and rate_limited counts
        """
        reminders = self.get_due_reminders()
        sent = 0
        failed = 0
        rate_limited = 0
        
        for reminder in reminders[:batch_size]:
            try:
                # Check if client opted out
                if self.state.is_paused(reminder["invoice"]["client"]):
                    continue
                
                # Render and send email
                self.sender.send_collection_reminder(
                    to=reminder["invoice"]["email"],
                    template=reminder["template"],
                    invoice_data=reminder["invoice"]
                )
                
                # Update state
                self.state.record_email_sent(
                    reminder["invoice"]["client"],
                    reminder["invoice"]["number"],
                    reminder["rule"]
                )
                
                sent += 1
                
            except RateLimitExceeded:
                rate_limited += 1
                break  # Stop sending, will resume next cycle
                
            except Exception as e:
                failed += 1
                self.state.record_email_failed(
                    reminder["invoice"]["client"],
                    reminder["invoice"]["number"],
                    reminder["rule"],
                    str(e)
                )
        
        return {"sent": sent, "failed": failed, "rate_limited": rate_limited}