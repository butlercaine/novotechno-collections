# TASK: Graph API Email Client
**Task ID:** TASK_OAUTH_002
**Owner:** operations-agent-novotechno
**Type:** implementation
**Priority:** P0
**Status:** PENDING
**Created:** 2026-02-11 08:00 GMT-5

## Context
Implement Microsoft Graph API email client for sending collection reminders via Outlook. Must include token validation and refresh monitoring.

## Requirements

### 1. Token Validator with Refresh Monitoring
**File:** `novotechno-collections/src/auth/token_validator.py`

**Implementation:**
```python
import time
import logging
from datetime import datetime

class TokenValidator:
    def __init__(self, token_cache):
        self.cache = token_cache
        self.refresh_attempts = 0
        self.max_refresh_attempts = 3
        self.degraded_mode = False
        self.logger = logging.getLogger(__name__)
    
    def validate_before_request(self, buffer_seconds=300):
        """Check token expiry > buffer_seconds"""
        tokens = self.cache.load_tokens()
        if not tokens:
            raise Exception("No tokens found - OAuth not configured")
        
        expires_at = tokens.get("expires_at", 0)
        remaining = expires_at - time.time()
        
        if remaining < buffer_seconds:
            self.logger.warning(f"Token expires in {remaining}s (<{buffer_seconds}s buffer)")
            self._silent_refresh()
    
    def _silent_refresh(self):
        """Attempt silent refresh up to 3 times"""
        for attempt in range(self.max_refresh_attempts):
            try:
                result = self.cache.refresh_access_token()
                self.logger.info(f"Token refreshed successfully (attempt {attempt + 1})")
                self.refresh_attempts = 0
                return result
            except Exception as e:
                self.logger.error(f"Refresh failed (attempt {attempt + 1}): {e}")
                self.refresh_attempts += 1
        
        # After 3 failures, enter DEGRADED mode
        self.degraded_mode = True
        self.logger.critical("Token refresh failed 3x - DEGRADED MODE activated")
        self._notify_caine_degraded()
    
    def _notify_caine_degraded(self):
        """Notify Caine via sessions_send"""
        # Message to be sent when DEGRADED mode triggered
        message = {
            "type": "DEGRADED_MODE",
            "agent": "operations-agent-novotechno",
            "reason": "OAuth token refresh failed 3 consecutive times",
            "timestamp": datetime.utcnow().isoformat(),
            "action_required": "Interactive OAuth re-authentication required"
        }
        self.logger.critical(f"WOULD SEND: {message}")
    
    def log_refresh_audit(self, old_tid, new_tid):
        """Audit log for every refresh"""
        self.logger.info(f"TOKEN_REFRESH_AUDIT: old_tid={old_tid[:8]}... new_tid={new_tid[:8]}...")
```

**Acceptance Criteria:**
- [ ] Pre-send validation: check token expiry >300s
- [ ] Silent refresh attempts up to 3 times
- [ ] DEGRADED mode triggers after 3 failures
- [ ] Audit logging: old_tid, new_tid, timestamp
- [ ] Caine notification in DEGRADED mode

### 2. Graph API Email Sender
**File:** `novotechno-collections/src/collections/email_sender.py`

**Implementation:**
```python
import requests
from typing import List, Dict
import json

class GraphEmailSender:
    BASE_URL = "https://graph.microsoft.com/v1.0"
    
    def __init__(self, token_validator, rate_limiter):
        self.validator = token_validator
        self.rate_limiter = rate_limiter
        self.session = requests.Session()
        self.session.headers["Authorization"] = "Bearer {token}"
        self.session.headers["Content-Type"] = "application/json"
    
    def send_email(self, to_address: str, subject: str, body_html: str):
        """Send email via Graph API with rate limiting and retry"""
        
        # Check rate limit
        if not self.rate_limiter.consume():
            raise RateLimitExceeded("Rate limit exceeded - try again later")
        
        # Validate token
        self.validator.validate_before_request()
        
        # Build request
        email_data = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": body_html
                },
                "toRecipients": [{"emailAddress": {"address": to_address}}]
            },
            "saveToSentItems": True
        }
        
        # Send with retry
        return self._send_with_retry(email_data)
    
    def _send_with_retry(self, email_data, max_attempts=3):
        """Exponential backoff retry on 429"""
        for attempt in range(max_attempts):
            try:
                response = self.session.post(
                    f"{self.BASE_URL}/users/me/sendMail",
                    json=email_data
                )
                response.raise_for_status()
                return {"status": "sent", "message_id": response.headers.get("Message-ID")}
            
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    wait_time = 2 ** attempt  # 1s, 2s, 4s
                    time.sleep(wait_time)
                    continue
                raise
```

**Acceptance Criteria:**
- [ ] Graph API POST to /users/me/sendMail
- [ ] Token bucket enforcement
- [ ] Exponential backoff (1s, 2s, 4s) on 429
- [ ] Error handling for 401, 403
- [ ] Message-ID returned for tracking

### 3. Interactive OAuth Setup Script
**File:** `novotechno-collections/scripts/setup_oauth.py`

**Usage:**
```bash
python scripts/setup_oauth.py --client-id <id> --tenant-id <tenant> --scopes "Mail.Send offline_access"
```

**Implementation:**
```python
#!/usr/bin/env python3
import click
from src.auth.device_code_flow import DeviceCodeAuth
from src.auth.token_cache import TokenCache

@click.command()
@click.option("--client-id", required=True, help="Azure AD app client ID")
@click.option("--tenant-id", default="common", help="Tenant ID (default: common)")
@click.option("--scopes", default="Mail.Send offline_access", help="OAuth scopes")
def setup_oauth(client_id, tenant_id, scopes):
    """Interactive OAuth setup for Microsoft Graph API"""
    
    auth = DeviceCodeAuth(client_id, tenant_id, scopes.split())
    cache = TokenCache()
    
    # Step 1: Get device code
    flow = auth.acquire_device_code()
    
    print(f"\n🔐 Authentication Required")
    print(f"1. Open: {flow['verification_uri']}")
    print(f"2. Enter code: {flow['user_code']}")
    print(f"3. Complete authentication...")
    print(f"\n⏳ Waiting for authentication...")
    
    # Step 2: Poll for token
    result = auth.poll_for_token(flow)
    
    # Step 3: Cache tokens
    cache.save_tokens(
        access_token=result["access_token"],
        refresh_token=result["refresh_token"],
        expires_in=result["expires_in"]
    )
    
    print(f"\n✅ Authentication successful!")
    print(f"Token cached in macOS Keychain")
    
    # Step 4: Test email
    sender = GraphEmailSender(TokenValidator(cache), TokenBucket())
    sender.send_email(
        to_address="test@example.com",
        subject="NovotEcho Collections - Test Email",
        body_html="<p>OAuth setup complete!</p>"
    )
    print(f"✅ Test email sent successfully!")
```

**Acceptance Criteria:**
- [ ] Interactive device code flow
- [ ] User code displayed
- [ ] Tokens cached to Keychain
- [ ] Test email sent
- [ ] Error handling for auth failure

## Dependencies
- requests >= 2.28.0
- click for CLI

## Output Files
- `novotechno-collections/src/auth/token_validator.py` (200 lines)
- `novotechno-collections/src/collections/email_sender.py` (400 lines)
- `novotechno-collections/scripts/setup_oauth.py` (150 lines)
- `novotechno-collections/tests/test_token_validator.py` (120 lines)
- `novotechno-collections/tests/test_email_sender.py` (150 lines)

## Definition of Done
- [ ] Code implemented and committed
- [ ] Token validator tests pass
- [ ] Email sender tests pass
- [ ] Interactive setup script works end-to-end
- [ ] RESPONSE file written

## Previous Task
TASK_OAUTH_001 (device code flow & token caching) — dependency met
