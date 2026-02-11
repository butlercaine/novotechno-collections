"""
Microsoft Graph API email sender with rate limiting and retry logic.
Sends collection reminders via Outlook with proper error handling.
"""

import time
import logging
import requests
from typing import Dict, Any, Optional
from datetime import datetime
from src.auth.token_validator import TokenValidator
from src.auth.rate_limiter import TokenBucketRateLimiter
from src.auth.token_cache import TokenCache


logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded."""
    pass


class GraphEmailSender:
    """
    Microsoft Graph API email sender with token validation, rate limiting,
    and exponential backoff retry logic.
    """
    
    BASE_URL = "https://graph.microsoft.com/v1.0"
    
    def __init__(
        self,
        token_validator: TokenValidator,
        rate_limiter: TokenBucketRateLimiter,
        account_id: str,
        cache: Optional[TokenCache] = None
    ):
        """
        Initialize Graph API email sender.
        
        Args:
            token_validator: Token validator for authentication
            rate_limiter: Rate limiter for request throttling
            account_id: Account identifier for token retrieval
            cache: Optional token cache (if not in validator)
        """
        self.validator = token_validator
        self.rate_limiter = rate_limiter
        self.account_id = account_id
        self.cache = cache or token_validator.cache
        self.logger = logging.getLogger(f"{__name__}.{account_id}")
        
        # Initialize session
        self.session = requests.Session()
        self.session.headers["Content-Type"] = "application/json"
        
        logger.info(f"GraphEmailSender initialized for account {account_id}")
    
    def _get_valid_token(self) -> str:
        """
        Get valid access token, refreshing if necessary.
        
        Returns:
            Valid access token
            
        Raises:
            Exception: If token validation/refresh fails
        """
        token_info = self.validator.validate_before_request(self.account_id)
        return token_info["access_token"]
    
    def _update_session_auth(self, token: str):
        """Update session authorization header with new token."""
        self.session.headers["Authorization"] = f"Bearer {token}"
    
    def send_email(
        self,
        to_address: str,
        subject: str,
        body_html: str,
        cc_addresses: Optional[list] = None,
        bcc_addresses: Optional[list] = None,
        save_to_sent_items: bool = True
    ) -> Dict[str, Any]:
        """
        Send email via Graph API with rate limiting and retry logic.
        
        Args:
            to_address: Primary recipient email
            subject: Email subject
            body_html: HTML body content
            cc_addresses: Optional CC recipients
            bcc_addresses: Optional BCC recipients
            save_to_sent_items: Whether to save to sent items
            
        Returns:
            Dict with status and message_id
            
        Raises:
            RateLimitExceeded: If rate limit exceeded
            Exception: For other errors
        """
        # Check rate limit
        if not self.rate_limiter.try_acquire():
            raise RateLimitExceeded(
                f"Rate limit exceeded - cannot send to {to_address}"
            )
        
        # Validate token before request
        token = self._get_valid_token()
        self._update_session_auth(token)
        
        # Build email message
        email_data = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": body_html
                },
                "toRecipients": [
                    {"emailAddress": {"address": to_address}}
                ]
            },
            "saveToSentItems": save_to_sent_items
        }
        
        # Add CC recipients if provided
        if cc_addresses:
            email_data["message"]["ccRecipients"] = [
                {"emailAddress": {"address": addr}} for addr in cc_addresses
            ]
        
        # Add BCC recipients if provided
        if bcc_addresses:
            email_data["message"]["bccRecipients"] = [
                {"emailAddress": {"address": addr}} for addr in bcc_addresses
            ]
        
        # Send with retry logic
        return self._send_with_retry(email_data, to_address)
    
    def send_collection_reminder(
        self,
        to_address: str,
        debtor_name: str,
        amount: float,
        due_date: str,
        collection_id: str
    ) -> Dict[str, Any]:
        """
        Send collection reminder email with template.
        
        Args:
            to_address: Debtor email
            debtor_name: Debtor name
            amount: Amount owed
            due_date: Due date
            collection_id: Collection ID for tracking
            
        Returns:
            Send result dict
        """
        subject = f"NovotEcho Collections - Payment Reminder #{collection_id}"
        
        body_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #2c5aa0;">Payment Reminder</h2>
            
            <p>Dear {debtor_name},</p>
            
            <p>This is a reminder that payment of <strong>${amount:,.2f}</strong> is due by <strong>{due_date}</strong>.</p>
            
            <p><strong>Collection ID:</strong> {collection_id}</p>
            
            <p>Please make your payment promptly to avoid additional fees.</p>
            
            <p>If you have any questions or need to discuss payment arrangements, please contact us immediately.</p>
            
            <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
            
            <p style="font-size: 12px; color: #666;">
                This is an automated reminder from NovotEcho Collections.<br>
                Do not reply directly to this email. Contact collections@novotechno.local for assistance.
            </p>
        </body>
        </html>
        """
        
        return self.send_email(to_address, subject, body_html)
    
    def _send_with_retry(
        self,
        email_data: Dict[str, Any],
        recipient: str,
        max_attempts: int = 3
    ) -> Dict[str, Any]:
        """
        Send email with exponential backoff retry on 429 errors.
        
        Args:
            email_data: Email payload
            recipient: Recipient email (for logging)
            max_attempts: Maximum retry attempts
            
        Returns:
            Result dict with status and message_id
        """
        for attempt in range(max_attempts):
            try:
                self.logger.info(
                    f"Sending email to {recipient} (attempt {attempt + 1}/{max_attempts})"
                )
                
                response = self.session.post(
                    f"{self.BASE_URL}/users/me/sendMail",
                    json=email_data,
                    timeout=30
                )
                
                # Raise for 4xx/5xx errors
                response.raise_for_status()
                
                # Success
                message_id = response.headers.get("Message-ID", "unknown")
                self.logger.info(
                    f"Email sent successfully to {recipient} - Message-ID: {message_id}"
                )
                
                return {
                    "status": "sent",
                    "message_id": message_id,
                    "recipient": recipient,
                    "timestamp": datetime.utcnow().isoformat(),
                    "attempts": attempt + 1
                }
                
            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if e.response else 0
                
                if status_code == 429:  # Rate limited
                    if attempt < max_attempts - 1:
                        # Exponential backoff: 1s, 2s, 4s...
                        wait_time = 2  ** attempt
                        self.logger.warning(
                            f"Rate limited (429) for {recipient}, "
                            f"waiting {wait_time}s (attempt {attempt + 1})"
                        )
                        time.sleep(wait_time)
                        continue
                
                elif status_code == 401:  # Unauthorized
                    self.logger.error(
                        f"Authentication failed (401) for {recipient} - "
                        "Token may be expired or invalid"
                    )
                    raise Exception(
                        f"Authentication failed: {e.response.text if e.response else str(e)}"
                    )
                
                elif status_code == 403:  # Forbidden
                    self.logger.error(
                        f"Permission denied (403) for {recipient} - "
                        "Check Graph API permissions (Mail.Send)"
                    )
                    raise Exception(
                        f"Permission denied: {e.response.text if e.response else str(e)}"
                    )
                
                else:
                    self.logger.error(
                        f"HTTP error {status_code} sending to {recipient}: {e}"
                    )
                    if attempt == max_attempts - 1:
                        raise Exception(
                            f"Failed to send email after {max_attempts} attempts: {e}"
                        )
                
            except requests.exceptions.Timeout:
                self.logger.warning(
                    f"Timeout sending to {recipient} (attempt {attempt + 1})"
                )
                if attempt == max_attempts - 1:
                    raise Exception(
                        f"Email sending timed out after {max_attempts} attempts"
                    )
                time.sleep(2 ** attempt)  # Exponential backoff on timeout
                
            except Exception as e:
                self.logger.error(
                    f"Unexpected error sending to {recipient}: {e}",
                    exc_info=True
                )
                if attempt == max_attempts - 1:
                    raise
                time.sleep(2 ** attempt)
        
        # Should never reach here (return or raise above)
        raise Exception(f"Email sending failed after {max_attempts} attempts")
    
    def check_rate_limit_status(self) -> Dict[str, Any]:
        """
        Check current rate limit status.
        
        Returns:
            Rate limit status dict
        """
        return self.rate_limiter.get_status()
    
    def get_sending_stats(self) -> Dict[str, Any]:
        """
        Get email sending statistics for monitoring.
        
        Returns:
            Stats dict with counts and timestamps
        """
        status = self.check_rate_limit_status()
        validator_status = self.validator.get_status(self.account_id)
        
        return {
            "rate_limit_status": status,
            "validator_status": validator_status,
            "account": self.account_id,
            "timestamp": datetime.utcnow().isoformat()
        }