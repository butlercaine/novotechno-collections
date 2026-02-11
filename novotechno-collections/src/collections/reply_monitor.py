"""Reply monitor for handling client responses to collection emails."""

from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
import re


@dataclass
class ReplyAction:
    """Represents an action to take based on a reply."""
    action: str  # "pause", "mark_paid", "manual_review"
    client: str
    invoice: str
    reason: str


class ReplyMonitor:
    """Monitor inbox for client replies to collection emails."""
    
    REPLY_PATTERNS = {
        r"stop|detener|unsubscribe": "pause",
        r"pagado|pago|paid": "mark_paid",
        r"duda|dudas|pregunta|question|clarify": "manual_review",
    }
    
    def __init__(self, graph_client, state_manager):
        """Initialize reply monitor.
        
        Args:
            graph_client: Graph API client instance
            state_manager: State manager instance
        """
        self.graph = graph_client
        self.state = state_manager
        self.last_check = None
    
    def get_collection_senders(self) -> List[str]:
        """Get list of collection email senders.
        
        Returns:
            List of email addresses
        """
        # Get configured sender email from state or config
        config = self.state.get_config() or {}
        sender_email = config.get("email", {}).get("sender_address")
        return [sender_email] if sender_email else []
    
    def check_replies(self) -> List[ReplyAction]:
        """Check inbox for replies to collection emails.
        
        Returns:
            List of reply actions
        """
        replies = []
        
        # Get messages since last check
        messages = self.graph.get_messages(
            received_after=self.last_check,
            sender_addresses=self.get_collection_senders()
        )
        
        for message in messages:
            action = self._parse_reply(message)
            if action:
                replies.append(action)
        
        self.last_check = datetime.utcnow().isoformat()
        return replies
    
    def _parse_reply(self, message: Dict) -> Optional[ReplyAction]:
        """Parse reply and determine action.
        
        Args:
            message: Email message dictionary
            
        Returns:
            ReplyAction if action needed, None otherwise
        """
        subject = message.get("subject", "")
        body = message.get("body", {}).get("content", "")
        content = f"{subject} {body}".lower()
        
        # Extract invoice number
        invoice_match = re.search(r"factura\s*#?\s*:?\s*([A-Z0-9-]+)", content, re.IGNORECASE)
        if not invoice_match:
            invoice_match = re.search(r"invoice\s*#?\s*:?\s*([A-Z0-9-]+)", content, re.IGNORECASE)
        
        invoice_number = invoice_match.group(1) if invoice_match else "unknown"
        
        # Extract sender email
        sender_email = ""
        from_address = message.get("from", {}).get("emailAddress", {})
        if from_address:
            sender_email = from_address.get("address", "")
        
        # Determine action
        for pattern, action in self.REPLY_PATTERNS.items():
            if re.search(pattern, content):
                return ReplyAction(
                    action=action,
                    client=sender_email,
                    invoice=invoice_number,
                    reason=f"Matched pattern: {pattern}"
                )
        
        return None
    
    def execute_actions(self, actions: List[ReplyAction]):
        """Execute reply actions.
        
        Args:
            actions: List of ReplyAction objects
        """
        for action in actions:
            if action.action == "pause":
                self.state.pause_collection(action.client)
                self._notify_account_manager(action)
                
            elif action.action == "mark_paid":
                self.state.mark_paid_by_reply(action.client, action.invoice)
                
            elif action.action == "manual_review":
                self.state.queue_for_review(action.client, action.invoice)
    
    def _notify_account_manager(self, action: ReplyAction):
        """Notify account manager of opt-out."""
        # Implementation for notifying account manager
        # This could send an email or create a notification
        print(f"[NOTIFY] Client {action.client} paused collections")


class GraphClient:
    """Stub Graph API client for ReplyMonitor."""
    
    def get_messages(self, received_after: Optional[str] = None, sender_addresses: Optional[List[str]] = None) -> List[Dict]:
        """Get messages from Graph API.
        
        Args:
            received_after: Filter messages received after this timestamp
            sender_addresses: Filter messages from these senders
            
        Returns:
            List of message dictionaries
        """
        # This is a stub - in real implementation would call Graph API
        return []