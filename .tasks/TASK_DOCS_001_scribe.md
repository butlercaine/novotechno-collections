# TASK: OAuth Setup Runbook & Documentation
**Task ID:** TASK_DOCS_001
**Owner:** scribe-novotechno
**Type:** documentation
**Priority:** P1
**Status:** PENDING
**Created:** 2026-02-11 08:00 GMT-5

## Context
Create comprehensive OAuth setup runbook and update project documentation. This ensures future maintainers can set up OAuth without developer assistance.

## Requirements

### 1. OAuth Setup Runbook
**File:** `novotechno-collections/docs/oauth-setup.md`

**Content:**
```markdown
# OAuth Setup Runbook

**Last Updated:** 2026-02-11
**Version:** 1.0

---

## Prerequisites

- Azure AD tenant with admin access
- Python 3.9+
- NovotEcho Collections installed (`pip install -e .`)

---

## Step 1: Register Application in Azure AD

### 1.1 Navigate to Azure Portal
1. Go to: https://portal.azure.com
2. Search for "Azure Active Directory"
3. Select "App registrations" → "New registration"

### 1.2 Register Application
```
Name: NovotEcho Collections
Supported account types: Accounts in this organizational directory only
Redirect URI: Public client/native (mobile & desktop applications)
           : http://localhost
```

### 1.3 Note Important Values
After registration, note these values:
- **Application (client) ID:** XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX
- **Directory (tenant) ID:** XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX

### 1.4 Create Client Secret
1. Go to "Certificates & secrets"
2. New client secret
3. Description: "NovotEcho Collections Production"
4. Expires: 12 months (or your policy)
5. **IMPORTANT:** Copy the secret value immediately - it won't be shown again

### 1.5 Configure API Permissions
1. Go to "API permissions"
2. Add permission: Microsoft Graph → Delegated permissions
3. Select:
   - `Mail.Send` - Send emails
   - `Mail.Read` - Monitor replies  
   - `offline_access` - Refresh tokens
   - `User.Read` - Verify sender identity
4. Click "Grant admin consent" (required for some tenants)

---

## Step 2: Configure Local Environment

### 2.1 Set Environment Variables

Create `~/.bashrc` or `~/.zshrc` additions:
```bash
export NOVO_CLIENT_ID="your-client-id"
export NOVO_CLIENT_SECRET="your-client-secret"
export NOVO_TENANT_ID="your-tenant-id"
```

### 2.2 Create Configuration File

Create `~/.config/novotechno-collections/config.yaml`:
```yaml
oauth:
  client_id: ${NOVO_CLIENT_ID}
  client_secret: ${NOVO_CLIENT_SECRET}
  tenant_id: ${NOVO_TENANT_ID}
  scopes:
    - Mail.Send
    - Mail.Read
    - offline_access
    - User.Read

email:
  sender: "cobranzas@novotechno.com"
  reply_to: "soporte@novotechno.com"
  
rate_limits:
  per_cycle: 20
  per_day: 100
  cycle_seconds: 300

paths:
  invoices: ~/Documents/Invoices/
  archive: ~/Documents/Invoices/paid/
  state: ~/.local/share/novotechno-collections/state/
```

---

## Step 3: Initial OAuth Setup

### 3.1 Run Setup Script

```bash
cd /path/to/novotechno-collections
python scripts/setup_oauth.py
```

### 3.2 Follow Interactive Prompts

```
🚀 OAuth Setup Starting...

🔐 Step 1: Device Code Flow
1. Opening browser to: https://microsoft.com/devicelogin
2. Enter code: XXXXXXXX
3. Complete authentication...

⏳ Waiting for authentication...
✅ Authentication successful!
✅ Token cached in macOS Keychain
✅ Test email sent to your inbox

🎉 OAuth setup complete!
```

### 3.3 Verify Setup

```bash
# Check token is cached
python -c "from src.auth.token_cache import TokenCache; t = TokenCache(); print('✅ Token cached' if t.load_tokens() else '❌ No token')"

# Test email sending
python -c "
from src.auth.token_validator import TokenValidator
from src.collections.email_sender import GraphEmailSender
v = TokenValidator()
v.validate_before_request()
print('✅ Token valid for API calls')
"
```

---

## Step 4: Troubleshooting

### 4.1 Common Issues

#### "AADSTSXXXX: Invalid client secret"
- Verify client secret is correct (no extra spaces)
- Regenerate secret if needed

#### "AADSTS65001: User or administrator has not consented"
- Go to Azure Portal → App Registrations → Your App → API Permissions
- Click "Grant admin consent"

#### "Token expired during operation"
- This should trigger automatic silent refresh
- If frequent, check system clock synchronization

### 4.2 Token Cache Issues

#### Token not persisting after restart
```bash
# Check Keychain access
security find-generic-password -s "novotechno-collections"

# Reset token cache
rm ~/.cache/novotechno-collections/tokens.json
python scripts/setup_oauth.py
```

#### Keychain permission denied
```bash
# Grant Full Disk Access to Terminal
# System Preferences → Security & Privacy → Privacy → Full Disk Access
```

### 4.3 Rate Limiting

#### "429 Too Many Requests"
- Default: 20 emails per 5-minute cycle
- If hitting limit, increase `cycle_seconds` in config

---

## Step 5: Production Deployment

### 5.1 Production Secrets

**NEVER commit secrets to git!**

Use environment variables or secrets manager:
```bash
# Environment variables
export NOVO_CLIENT_ID="..."
export NOVO_CLIENT_SECRET="..."

# Or use AWS Secrets Manager / Azure Key Vault
```

### 5.2 Monitoring

Check token health:
```bash
python scripts/monitor_oauth.py --check
```

Alert thresholds:
- **WARNING:** Token expires in <5 minutes
- **CRITICAL:** Token refresh failed 3x
- **DEGRADED:** Manual auth required

### 5.3 Rotation

Rotate client secret every 90 days:
1. Azure Portal → App Registrations → Your App → Certificates & secrets
2. Create new secret
3. Update environment variables
4. Verify operation
5. Delete old secret

---

## Security Considerations

### Token Storage
- ✅ Tokens encrypted in macOS Keychain
- ✅ Tokens never logged
- ✅ Tokens never committed to git
- ❌ Never store tokens in plaintext files

### Permissions
- ✅ Least privilege: only required scopes
- ✅ Scopes documented above
- ❌ Never request unnecessary permissions

### Audit Trail
- All token refreshes logged
- All email sends logged
- All errors logged

---

## Quick Reference

| Command | Description |
|---------|-------------|
| `python scripts/setup_oauth.py` | Initial OAuth setup |
| `python scripts/monitor_oauth.py --check` | Check token health |
| `python scripts/test_email.py --send` | Send test email |
| `python scripts/reset_oauth.py` | Reset OAuth configuration |

### File Locations
| Purpose | Location |
|---------|----------|
| Config | `~/.config/novotechno-collections/config.yaml` |
| Tokens | macOS Keychain (`novotechno-collections`) |
| State | `~/.local/share/novotechno-collections/state/` |
| Logs | `~/.cache/novotechno-collections/logs/` |

---

## Support

**Issues?** Check:
1. This runbook's troubleshooting section
2. Logs: `~/.cache/novotechno-collections/logs/`
3. Azure AD admin for permission issues
```

### 2. Update DECISIONS.md
**File:** `novotechno-collections/DECISIONS.md`

Add OAuth-related decisions:
```markdown
### [2026-02-11] - OAuth Security Architecture

**Decision:** Use MSAL device code flow with macOS Keychain storage

**Rationale:**
- Device code flow: No browser required in agent context
- Keychain: Secure storage with OS-level encryption
- MSAL: Official Microsoft library, actively maintained

**Alternatives Considered:**
- Interactive browser flow: Rejected (requires browser in agent)
- File-based token storage: Rejected (less secure than Keychain)
- Custom OAuth implementation: Rejected (security risk)

**Consequences:**
- Tokens survive agent restart
- Tokens never in plaintext
- Silent refresh prevents auth interruption

**References:**
- MSAL Python: https://github.com/AzureAD/microsoft-authentication-library-for-python
- Azure AD App Registration: docs.microsoft.com/azure/active-directory/develop/
```

### 3. Architecture Documentation
**File:** `novotechno-collections/docs/architecture/overview.md`

```markdown
# System Architecture

## Overview

NovotEcho Collections is an automated invoice collections system consisting of 3 agents:

1. **collections-emailer** - Monitors invoices, sends reminder emails
2. **payment-watcher** - Detects payments via filesystem monitoring
3. **collections-supervisor** - Coordinates agents, monitors health

## Data Flow

```
Invoice PDF → Parser → State File → Scheduler → Email
                                       ↓
Payment Detected → State Update → Archive
                         ↓
                  Supervisor Dashboard
```

## Agent Communication

Agents communicate via:
- **File-based queues:** JSONL files in `~/.cache/novotechno-collections/queues/`
- **Shared state:** SQLite or JSON files in `~/.local/share/novotechno-collections/state/`
- **Events:** File system events via watchdog (payment-watcher)

## OAuth Security

- **Flow:** MSAL device code flow
- **Storage:** macOS Keychain (never plaintext)
- **Refresh:** Automatic silent refresh <5 min before expiry
- **Monitoring:** Token validator tracks refresh success/failure

## Rate Limiting

- **Per Cycle:** 20 emails per 5 minutes
- **Per Day:** 100 emails per tenant
- **Backoff:** Exponential (1s, 2s, 4s) on 429 errors

## State Management

- **Format:** JSON with SHA-256 checksums
- **Writes:** Atomic (`.tmp` → `os.replace()`)
- **Audit:** Append-only event log
- **Reconciliation:** Hourly ledger vs state check

## Patterns Extracted

During development, the following patterns were identified for reuse:

- **PAT-065:** Agent Heartbeat Protocol - Supervisor monitoring agents
- **PAT-066:** Event-Driven Agent Coordination - File-based messages
- **PAT-067:** Confidence-Based Validation - PDF scoring routing
```

## Dependencies
- TASK_OAUTH_001 (must complete first)
- TASK_OAUTH_002 (must complete first)

## Output Files
- `novotechno-collections/docs/oauth-setup.md` (comprehensive runbook)
- `novotechno-collections/DECISIONS.md` (updated with OAuth decisions)
- `novotechno-collections/docs/architecture/overview.md` (architecture doc)

## Definition of Done
- [ ] OAuth runbook complete and testable
- [ ] All troubleshooting scenarios covered
- [ ] DECISIONS.md updated
- [ ] Architecture documentation created
- [ ] RESPONSE file written

## Success Criteria
- [ ] Maintainer can set up OAuth independently using runbook
- [ ] Troubleshooting section covers common issues
- [ ] Security considerations documented
- [ ] Quick reference section usable

## Previous Task
TASK_OAUTH_001, TASK_OAUTH_002 (both must complete first)

## Next Task
TASK_GIT_001 (release) — depends on all QA validation
