# TASK: MSAL Device Code Flow & Token Caching
**Task ID:** TASK_OAUTH_001
**Owner:** operations-agent-novotechno
**Type:** implementation
**Priority:** P0
**Status:** PENDING
**Created:** 2026-02-11 08:00 GMT-5

## Context
Implement secure OAuth device code flow for Microsoft Graph API without browser auth in agent context. Pre-production requirement: token persistence validation (C-008).

## Requirements

### 1. MSAL Device Code Flow Implementation
**File:** `novotechno-collections/src/auth/device_code_flow.py`

**Implementation:**
```python
from msal import PublicClientApplication
import time

class DeviceCodeAuth:
    def __init__(self, client_id, tenant_id, scopes):
        self.app = PublicClientApplication(
            client_id=client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}"
        )
        self.scopes = scopes
    
    def acquire_device_code(self):
        flow = self.app.initiate_device_flow(scopes=self.scopes)
        return flow  # device_code, user_code, verification_uri, expires_in
    
    def poll_for_token(self, flow):
        # Poll every 5s for max 15 minutes
        while True:
            result = self.app.acquire_token_by_device_flow(flow)
            if result.get("access_token"):
                return result  # access_token, refresh_token, id_token, expires_in
            time.sleep(5)
```

**Acceptance Criteria:**
- [ ] Device code acquired successfully
- [ ] User code displayed for authorization
- [ ] Token response parsed: access_token, refresh_token, id_token, expires_in
- [ ] Error handling for expired_token, authorization_declined
- [ ] Polling timeout (15 min) implemented
- [ ] Unit tests: mock device flow responses, test error cases

### 2. Token Cache with Keychain Integration
**File:** `novotechno-collections/src/auth/token_cache.py`

**Implementation:**
```python
from msal import KeychainPersistence
import json

class TokenCache:
    def __init__(self):
        self.keychain = KeychainPersistence(
            service_name="novotechno-collections",
            account_name="outlook_token"
        )
        self.tokens = {"access_token": None, "refresh_token": None, "expires_at": None}
    
    def save_tokens(self, access_token, refresh_token, expires_in):
        # Securely store in Keychain
        data = json.dumps({
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": time.time() + expires_in
        })
        self.keychain.save(data.encode())
    
    def load_tokens(self):
        # Load from Keychain
        data = self.keychain.load()
        if data:
            return json.loads(data.decode())
        return None
    
    def is_token_valid(self, buffer_seconds=300):
        # Check if token expires > buffer time
        tokens = self.load_tokens()
        if not tokens:
            return False
        return time.time() < (tokens["expires_at"] - buffer_seconds)
```

**Acceptance Criteria:**
- [ ] Tokens stored in macOS Keychain (never plaintext)
- [ ] Keychain ACLs set to `kSecAttrAccessibleWhenUnlocked`
- [ ] Tokens survive agent restart (verify persistence)
- [ ] Token validity check with buffer (<300s) works
- [ ] Encrypted file fallback functional
- [ ] Unit tests: test save/load, test persistence

### 3. Token Bucket Rate Limiting
**File:** `novotechno-collections/src/auth/rate_limiter.py`

**Implementation:**
```python
import time
from threading import Lock

class TokenBucket:
    def __init__(self, capacity=20, refill_rate=0.2):  # 1 token per 5s
        self.capacity = capacity
        self.tokens = capacity
        self.refill_rate = refill_rate
        self.last_refill = time.time()
        self.lock = Lock()
    
    def consume(self, tokens=1):
        with self.lock:
            self._refill()
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False  # Rate limit exceeded
    
    def _refill(self):
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
```

**Usage:** Enforce 20 emails/cycle, 100/day tenant limit

**Acceptance Criteria:**
- [ ] Token bucket enforces 20 emails per heartbeat cycle
- [ ] Refill rate: 1 token per 5 seconds
- [ ] Exponential backoff triggers on 429 responses
- [ ] Token bucket state persists to file
- [ ] Test with 21 emails → 20 sent, 1 queued for next cycle

### 4. Exponential Backoff on 429
**Integration:** In email sender

```python
def send_with_retry(self, email_data, max_attempts=3):
    for attempt in range(max_attempts):
        try:
            return self._send_email(email_data)
        except RateLimitError:
            wait = 2  ** attempt  # 1s, 2s, 4s
            time.sleep(wait)
    raise Exception("Max retries exceeded")
```

**Acceptance Criteria:**
- [ ] Exponential backoff: 1s, 2s, 4s delays
- [ ] Max 3 attempts before failure
- [ ] Logs each retry attempt

## Output Files
- `novotechno-collections/src/auth/__init__.py`
- `novotechno-collections/src/auth/device_code_flow.py` (200 lines)
- `novotechno-collections/src/auth/token_cache.py` (250 lines)
- `novotechno-collections/src/auth/rate_limiter.py` (100 lines)
- `novotechno-collections/tests/test_device_code_flow.py` (100 lines)
- `novotechno-collections/tests/test_token_cache.py` (80 lines)
- `novotechno-collections/tests/test_token_bucket.py` (80 lines)

## Dependencies
- msal >= 1.20.0
- pytest for testing

## Definition of Done
- [ ] Code implemented and committed to GitHub
- [ ] All unit tests pass
- [ ] Token persists across 3 test restarts
- [ ] Rate limiting test passes (21 emails → 20 sent)
- [ ] RESPONSE file written: `~/.openclaw/workspace-operations-agent-novotechno/.tasks/TASK_OAUTH_001_RESPONSE.md`

## Next Task
TASK_OAUTH_002 (Graph API email client) — dependent on this task
