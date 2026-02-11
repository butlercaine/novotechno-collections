"""
Unit Tests for Collection Scheduler
Project: PROJ-2026-0210-novotechno-collections
"""

import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock
from datetime import datetime, timedelta

# Add paths - use src/collections like other tests
SRC_PATH = Path(__file__).parent.parent / 'src' / 'collections'
sys.path.insert(0, str(SRC_PATH))

import pytest
from scheduler import CollectionScheduler, RateLimitExceeded


@pytest.fixture
def mock_sender():
    """Create mock email sender."""
    sender = Mock()
    sender.send_collection_reminder = Mock()
    return sender


@pytest.fixture
def mock_state():
    """Create mock state manager."""
    state = Mock()
    
    # Setup default returns
    state.get_all_unpaid = Mock(return_value=[])
    state.is_paused = Mock(return_value=False)
    state.record_email_sent = Mock()
    state.record_email_failed = Mock()
    
    return state


@pytest.fixture
def scheduler(mock_sender, mock_state):
    """Create scheduler instance."""
    return CollectionScheduler(mock_sender, mock_state)


class TestReminderRules:
    """Test reminder scheduling rules."""
    
    def test_reminder_rules_structure(self, scheduler):
        """Test reminder rules are properly defined."""
        assert len(scheduler.REMINDER_RULES) == 6
        assert "reminder_1" in scheduler.REMINDER_RULES
        assert "reminder_2" in scheduler.REMINDER_RULES
        assert "overdue_1" in scheduler.REMINDER_RULES
        assert "escalation" in scheduler.REMINDER_RULES
    
    def test_reminder_1_timing(self, scheduler):
        """Test reminder_1 is 3 days before due."""
        rule = scheduler.REMINDER_RULES["reminder_1"]
        assert rule["days_before_due"] == 3
        assert rule["template"] == "reminder_3d"
    
    def test_reminder_2_timing(self, scheduler):
        """Test reminder_2 is on due date."""
        rule = scheduler.REMINDER_RULES["reminder_2"]
        assert rule["days_before_due"] == 0
        assert rule["template"] == "reminder_due"
    
    def test_overdue_timings(self, scheduler):
        """Test overdue reminder timings."""
        assert scheduler.REMINDER_RULES["overdue_1"]["days_after_due"] == 5
        assert scheduler.REMINDER_RULES["overdue_2"]["days_after_due"] == 7
        assert scheduler.REMINDER_RULES["final_notice"]["days_after_due"] == 10
        assert scheduler.REMINDER_RULES["escalation"]["days_after_due"] == 14


class TestGetDueReminders:
    """Test getting due reminders."""
    
    def test_no_unpaid_invoices(self, scheduler, mock_state):
        """Test no reminders when no unpaid invoices."""
        mock_state.get_all_unpaid.return_value = []
        
        reminders = scheduler.get_due_reminders()
        
        assert len(reminders) == 0
    
    def test_reminder_3_days_before(self, scheduler, mock_state):
        """Test reminder triggered 3 days before due."""
        # Use a fixed time provider for testing
        fixed_time = datetime(2026, 2, 11, 12, 0, 0)
        scheduler._time_provider = lambda: fixed_time
        
        due_date = (fixed_time + timedelta(days=3)).isoformat()
        invoice = {
            "number": "INV-001",
            "client": "Client A",
            "email": "client@example.com",
            "due_date": due_date,
            "amount": 1000.0
        }
        mock_state.get_all_unpaid.return_value = [invoice]
        
        reminders = scheduler.get_due_reminders()
        
        assert len(reminders) == 1
        assert reminders[0]["rule"] == "reminder_1"
        assert reminders[0]["template"] == "reminder_3d"
        assert reminders[0]["days_until_due"] == 3
    
    def test_reminder_on_due_date(self, scheduler, mock_state):
        """Test reminder on due date."""
        fixed_time = datetime(2026, 2, 11, 12, 0, 0)
        scheduler._time_provider = lambda: fixed_time
        
        due_date = fixed_time.isoformat()
        invoice = {
            "number": "INV-002",
            "client": "Client B",
            "email": "clientb@example.com",
            "due_date": due_date,
            "amount": 2000.0
        }
        mock_state.get_all_unpaid.return_value = [invoice]
        
        reminders = scheduler.get_due_reminders()
        
        assert len(reminders) == 1
        assert reminders[0]["rule"] == "reminder_2"
        assert reminders[0]["template"] == "reminder_due"
    
    def test_overdue_reminder(self, scheduler, mock_state):
        """Test overdue reminder."""
        fixed_time = datetime(2026, 2, 11, 12, 0, 0)
        scheduler._time_provider = lambda: fixed_time
        
        due_date = (fixed_time - timedelta(days=5)).isoformat()
        invoice = {
            "number": "INV-003",
            "client": "Client C",
            "email": "clientc@example.com",
            "due_date": due_date,
            "amount": 3000.0
        }
        mock_state.get_all_unpaid.return_value = [invoice]
        
        reminders = scheduler.get_due_reminders()
        
        assert len(reminders) == 1
        assert reminders[0]["rule"] == "overdue_1"
        assert reminders[0]["template"] == "overdue_5d"
        assert reminders[0]["days_overdue"] == 5
    
    def test_multiple_invoices_different_stages(self, scheduler, mock_state):
        """Test multiple invoices at different reminder stages."""
        fixed_time = datetime(2026, 2, 11, 12, 0, 0)
        scheduler._time_provider = lambda: fixed_time
        
        now = fixed_time
        invoices = [
            {
                "number": "INV-001",
                "client": "Client A",
                "email": "clienta@example.com",
                "due_date": (now + timedelta(days=3)).isoformat(),
                "amount": 1000.0
            },
            {
                "number": "INV-002",
                "client": "Client B",
                "email": "clientb@example.com",
                "due_date": now.isoformat(),
                "amount": 2000.0
            },
            {
                "number": "INV-003",
                "client": "Client C",
                "email": "clientc@example.com",
                "due_date": (now - timedelta(days=5)).isoformat(),
                "amount": 3000.0
            }
        ]
        mock_state.get_all_unpaid.return_value = invoices
        
        reminders = scheduler.get_due_reminders()
        
        # Each invoice should trigger one reminder
        assert len(reminders) == 3
    
    def test_paused_client_skipped_in_listing(self, scheduler, mock_state):
        """Test paused clients appear in reminders list (filtering happens in send)."""
        fixed_time = datetime(2026, 2, 11, 12, 0, 0)
        scheduler._time_provider = lambda: fixed_time
        
        due_date = (fixed_time + timedelta(days=3)).isoformat()
        invoice = {
            "number": "INV-001",
            "client": "Client A",
            "email": "client@example.com",
            "due_date": due_date,
            "amount": 1000.0,
            "paused": True
        }
        mock_state.get_all_unpaid.return_value = [invoice]
        mock_state.is_paused.return_value = True
        
        # This should appear in reminders list (get_due_reminders doesn't filter by pause)
        reminders = scheduler.get_due_reminders()
        assert len(reminders) == 1


class TestSendReminders:
    """Test sending reminders."""
    
    def test_send_single_reminder(self, scheduler, mock_sender, mock_state):
        """Test sending a single reminder."""
        fixed_time = datetime(2026, 2, 11, 12, 0, 0)
        scheduler._time_provider = lambda: fixed_time
        
        due_date = (fixed_time + timedelta(days=3)).isoformat()
        invoice = {
            "number": "INV-001",
            "client": "Client A",
            "email": "client@example.com",
            "due_date": due_date,
            "amount": 1000.0
        }
        mock_state.get_all_unpaid.return_value = [invoice]
        
        result = scheduler.send_reminders()
        
        assert result["sent"] == 1
        assert result["failed"] == 0
        assert result["rate_limited"] == 0
        
        # Verify email was sent
        mock_sender.send_collection_reminder.assert_called_once()
        
        # Verify state was updated
        mock_state.record_email_sent.assert_called_once()
    
    def test_batch_size_respected(self, scheduler, mock_sender, mock_state):
        """Test batch size limit is respected."""
        fixed_time = datetime(2026, 2, 11, 12, 0, 0)
        scheduler._time_provider = lambda: fixed_time
        
        invoices = []
        for i in range(25):  # More than batch size
            invoices.append({
                "number": f"INV-{i:03d}",
                "client": f"Client {i}",
                "email": f"client{i}@example.com",
                "due_date": (fixed_time + timedelta(days=3)).isoformat(),
                "amount": 1000.0 + i * 100
            })
        mock_state.get_all_unpaid.return_value = invoices
        
        result = scheduler.send_reminders(batch_size=20)
        
        assert result["sent"] == 20
        assert mock_sender.send_collection_reminder.call_count == 20
    
    def test_rate_limit_exceeded(self, scheduler, mock_sender, mock_state):
        """Test rate limit handling."""
        fixed_time = datetime(2026, 2, 11, 12, 0, 0)
        scheduler._time_provider = lambda: fixed_time
        
        # Configure sender to raise RateLimitExceeded
        mock_sender.send_collection_reminder.side_effect = RateLimitExceeded("Rate limit")
        
        due_date = (fixed_time + timedelta(days=3)).isoformat()
        invoice = {
            "number": "INV-001",
            "client": "Client A",
            "email": "client@example.com",
            "due_date": due_date,
            "amount": 1000.0
        }
        mock_state.get_all_unpaid.return_value = [invoice]
        
        result = scheduler.send_reminders()
        
        assert result["sent"] == 0
        assert result["rate_limited"] == 1
        # Should stop processing after rate limit
        mock_state.record_email_failed.assert_not_called()
    
    def test_sender_exception_handled(self, scheduler, mock_sender, mock_state):
        """Test sender exceptions are handled gracefully."""
        fixed_time = datetime(2026, 2, 11, 12, 0, 0)
        scheduler._time_provider = lambda: fixed_time
        
        # Configure sender to raise generic exception
        mock_sender.send_collection_reminder.side_effect = Exception("SMTP error")
        
        due_date = (fixed_time + timedelta(days=3)).isoformat()
        invoice = {
            "number": "INV-001",
            "client": "Client A",
            "email": "client@example.com",
            "due_date": due_date,
            "amount": 1000.0
        }
        mock_state.get_all_unpaid.return_value = [invoice]
        
        result = scheduler.send_reminders()
        
        assert result["sent"] == 0
        assert result["failed"] == 1
        
        # Verify failure was recorded
        mock_state.record_email_failed.assert_called_once()
    
    def test_paused_client_not_sent(self, scheduler, mock_sender, mock_state):
        """Test reminders not sent to paused clients."""
        fixed_time = datetime(2026, 2, 11, 12, 0, 0)
        scheduler._time_provider = lambda: fixed_time
        
        due_date = (fixed_time + timedelta(days=3)).isoformat()
        invoice = {
            "number": "INV-001",
            "client": "Client A",
            "email": "client@example.com",
            "due_date": due_date,
            "amount": 1000.0
        }
        mock_state.get_all_unpaid.return_value = [invoice]
        mock_state.is_paused.return_value = True
        
        result = scheduler.send_reminders()
        
        assert result["sent"] == 0
        # Should not call sender for paused clients
        mock_sender.send_collection_reminder.assert_not_called()


class TestRateLimitException:
    """Test RateLimitExceeded exception."""
    
    def test_rate_limit_exception(self):
        """Test RateLimitExceeded exception can be raised and caught."""
        try:
            raise RateLimitExceeded("Test")
        except RateLimitExceeded as e:
            assert str(e) == "Test"
        except Exception:
            pytest.fail("RateLimitExceeded should be catchable as its own type")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])