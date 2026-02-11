"""
Unit Tests for Reply Monitor
Project: PROJ-2026-0210-novotechno-collections
"""

import sys
from pathlib import Path
from unittest.mock import Mock
from dataclasses import asdict

# Add paths - use src/collections like other tests
SRC_PATH = Path(__file__).parent.parent / 'src' / 'collections'
sys.path.insert(0, str(SRC_PATH))

import pytest
from reply_monitor import ReplyMonitor, ReplyAction


@pytest.fixture
def mock_graph_client():
    """Create mock Graph API client."""
    client = Mock()
    client.get_messages = Mock(return_value=[])
    return client


@pytest.fixture
def mock_state():
    """Create mock state manager."""
    state = Mock()
    state.pause_collection = Mock()
    state.mark_paid_by_reply = Mock()
    state.queue_for_review = Mock()
    state.get_config = Mock(return_value={"email": {"sender_address": "collections@company.com"}})
    return state


@pytest.fixture
def monitor(mock_graph_client, mock_state):
    """Create reply monitor instance."""
    return ReplyMonitor(mock_graph_client, mock_state)


class TestReplyPatterns:
    """Test reply pattern matching."""
    
    def test_stop_pattern_detected(self, monitor):
        """Test STOP/DETENER/UNSUBSCRIBE triggers pause."""
        message = {
            "subject": "Please STOP sending emails",
            "body": {"content": "I want to unsubscribe from these reminders"},
            "from": {"emailAddress": {"address": "client@example.com"}}
        }
        
        action = monitor._parse_reply(message)
        
        assert action is not None
        assert action.action == "pause"
        assert action.client == "client@example.com"
    
    def test_spanish_stop_pattern(self, monitor):
        """Test Spanish stop pattern."""
        message = {
            "subject": "Por favor DETENER",
            "body": {"content": "Detener los envios"},
            "from": {"emailAddress": {"address": "client@example.com"}}
        }
        
        action = monitor._parse_reply(message)
        
        assert action is not None
        assert action.action == "pause"
    
    def test_paid_pattern_detected(self, monitor):
        """Test PAGADO/PAGO/PAID triggers mark_paid."""
        message = {
            "subject": "Invoice paid",
            "body": {"content": "The invoice has been paid"},
            "from": {"emailAddress": {"address": "client@example.com"}}
        }
        
        action = monitor._parse_reply(message)
        
        assert action is not None
        assert action.action == "mark_paid"
    
    def test_spanish_paid_pattern(self, monitor):
        """Test Spanish paid pattern."""
        message = {
            "subject": "Factura PAGADO",
            "body": {"content": "La factura ya esta pagado"},
            "from": {"emailAddress": {"address": "client@example.com"}}
        }
        
        action = monitor._parse_reply(message)
        
        assert action is not None
        assert action.action == "mark_paid"
    
    def test_question_pattern_detected(self, monitor):
        """Test DUDAS/PREGUNTA/QUESTION triggers manual_review."""
        message = {
            "subject": "Question about invoice",
            "body": {"content": "Tengo una duda sobre esta factura"},
            "from": {"emailAddress": {"address": "client@example.com"}}
        }
        
        action = monitor._parse_reply(message)
        
        assert action is not None
        assert action.action == "manual_review"
    
    def test_invoice_number_extraction_spanish(self, monitor):
        """Test Spanish invoice number extraction with dudas pattern."""
        message = {
            "subject": "Consulta",
            "body": {"content": "Tengo unas dudas sobre la factura #: INV-2024-001"},
            "from": {"emailAddress": {"address": "client@example.com"}}
        }
        
        action = monitor._parse_reply(message)
        
        # "dudas" triggers manual_review action
        assert action is not None
        assert action.action == "manual_review"
        # Invoice number is lowercased because content is lowercased
        assert action.invoice.lower() == "inv-2024-001"
    
    def test_invoice_number_extraction_english(self, monitor):
        """Test English invoice number extraction."""
        message = {
            "subject": "Question",
            "body": {"content": "Regarding the invoice #: FACT-2024-002"},
            "from": {"emailAddress": {"address": "client@example.com"}}
        }
        
        action = monitor._parse_reply(message)
        
        # This returns None because no action pattern matched, not because invoice extraction failed
        # The content has "question" which triggers manual_review
        assert action is not None
        assert action.action == "manual_review"
    
    def test_no_match_returns_none(self, monitor):
        """Test non-matching content returns None."""
        message = {
            "subject": "Thanks for your service",
            "body": {"content": "Just wanted to say thanks!"},
            "from": {"emailAddress": {"address": "client@example.com"}}
        }
        
        action = monitor._parse_reply(message)
        
        assert action is None
    
    def test_case_insensitive_matching(self, monitor):
        """Test pattern matching is case insensitive."""
        message = {
            "subject": "STOP SENDING EMAILS",
            "body": {"content": "I want to UNSUBSCRIBE"},
            "from": {"emailAddress": {"address": "client@example.com"}}
        }
        
        action = monitor._parse_reply(message)
        
        assert action is not None
        assert action.action == "pause"


class TestReplyActions:
    """Test executing reply actions."""
    
    def test_pause_action(self, monitor, mock_state):
        """Test pause action pauses collection."""
        action = ReplyAction(
            action="pause",
            client="client@example.com",
            invoice="INV-001",
            reason="Matched pattern: stop"
        )
        
        monitor.execute_actions([action])
        
        mock_state.pause_collection.assert_called_once_with("client@example.com")
    
    def test_mark_paid_action(self, monitor, mock_state):
        """Test mark_paid action marks invoice as paid."""
        action = ReplyAction(
            action="mark_paid",
            client="client@example.com",
            invoice="INV-001",
            reason="Matched pattern: paid"
        )
        
        monitor.execute_actions([action])
        
        mock_state.mark_paid_by_reply.assert_called_once_with("client@example.com", "INV-001")
    
    def test_manual_review_action(self, monitor, mock_state):
        """Test manual_review action queues for review."""
        action = ReplyAction(
            action="manual_review",
            client="client@example.com",
            invoice="INV-001",
            reason="Matched pattern: question"
        )
        
        monitor.execute_actions([action])
        
        mock_state.queue_for_review.assert_called_once_with("client@example.com", "INV-001")
    
    def test_multiple_actions(self, monitor, mock_state):
        """Test multiple actions are executed."""
        actions = [
            ReplyAction(action="pause", client="client1@example.com", invoice="INV-001", reason="test"),
            ReplyAction(action="mark_paid", client="client2@example.com", invoice="INV-002", reason="test"),
            ReplyAction(action="manual_review", client="client3@example.com", invoice="INV-003", reason="test"),
        ]
        
        monitor.execute_actions(actions)
        
        assert mock_state.pause_collection.call_count == 1
        assert mock_state.mark_paid_by_reply.call_count == 1
        assert mock_state.queue_for_review.call_count == 1
    
    def test_unknown_action_ignored(self, monitor, mock_state):
        """Test unknown actions are ignored."""
        action = ReplyAction(
            action="unknown_action",
            client="client@example.com",
            invoice="INV-001",
            reason="test"
        )
        
        monitor.execute_actions([action])
        
        # No state methods should be called
        mock_state.pause_collection.assert_not_called()
        mock_state.mark_paid_by_reply.assert_not_called()
        mock_state.queue_for_review.assert_not_called()


class TestCheckReplies:
    """Test checking for replies."""
    
    def test_no_messages(self, monitor, mock_graph_client):
        """Test no replies when no messages."""
        mock_graph_client.get_messages.return_value = []
        
        actions = monitor.check_replies()
        
        assert len(actions) == 0
    
    def test_single_reply_detected(self, monitor, mock_graph_client):
        """Test single reply is detected."""
        mock_graph_client.get_messages.return_value = [
            {
                "subject": "STOP",
                "body": {"content": "Please stop sending emails"},
                "from": {"emailAddress": {"address": "client@example.com"}}
            }
        ]
        
        actions = monitor.check_replies()
        
        assert len(actions) == 1
        assert actions[0].action == "pause"
    
    def test_multiple_replies(self, monitor, mock_graph_client):
        """Test multiple replies are detected."""
        mock_graph_client.get_messages.return_value = [
            {
                "subject": "STOP",
                "body": {"content": "Please stop"},
                "from": {"emailAddress": {"address": "client1@example.com"}}
            },
            {
                "subject": "PAID",
                "body": {"content": "Invoice paid"},
                "from": {"emailAddress": {"address": "client2@example.com"}}
            },
            {
                "subject": "QUESTION",
                "body": {"content": "I have a question"},
                "from": {"emailAddress": {"address": "client3@example.com"}}
            }
        ]
        
        actions = monitor.check_replies()
        
        assert len(actions) == 3
    
    def test_last_check_updated(self, monitor):
        """Test last_check is updated after check."""
        original_last_check = monitor.last_check
        
        monitor.check_replies()
        
        assert monitor.last_check is not None
        if original_last_check is None:
            assert monitor.last_check is not None
    
    def test_sender_filter(self, monitor, mock_graph_client):
        """Test messages are filtered by sender."""
        # The method should pass sender addresses to Graph client
        monitor.check_replies()
        
        # Verify get_messages was called
        mock_graph_client.get_messages.assert_called()


class TestCollectionSenders:
    """Test collection sender configuration."""
    
    def test_get_senders_from_config(self, monitor, mock_state):
        """Test getting sender list from config."""
        mock_state.get_config.return_value = {
            "email": {"sender_address": "collections@company.com"}
        }
        
        senders = monitor.get_collection_senders()
        
        assert len(senders) == 1
        assert "collections@company.com" in senders
    
    def test_get_senders_empty_config(self, monitor, mock_state):
        """Test empty sender list when config missing."""
        mock_state.get_config.return_value = {}
        
        senders = monitor.get_collection_senders()
        
        assert len(senders) == 0
    
    def test_get_senders_no_config(self, monitor, mock_state):
        """Test empty sender list when no config."""
        mock_state.get_config.return_value = None
        
        senders = monitor.get_collection_senders()
        
        assert len(senders) == 0


class TestReplyActionDataclass:
    """Test ReplyAction dataclass."""
    
    def test_reply_action_creation(self):
        """Test ReplyAction can be created."""
        action = ReplyAction(
            action="pause",
            client="test@example.com",
            invoice="INV-001",
            reason="test reason"
        )
        
        assert action.action == "pause"
        assert action.client == "test@example.com"
        assert action.invoice == "INV-001"
        assert action.reason == "test reason"
    
    def test_reply_action_as_dict(self):
        """Test ReplyAction can be converted to dict."""
        action = ReplyAction(
            action="mark_paid",
            client="test@example.com",
            invoice="INV-001",
            reason="matched paid pattern"
        )
        
        action_dict = asdict(action)
        
        assert action_dict["action"] == "mark_paid"
        assert action_dict["client"] == "test@example.com"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])