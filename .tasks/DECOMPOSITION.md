# PROJ-2026-0210-novotechno-collections — Technical Decomposition

**Project:** Automated invoice collections system for NovotEcho
**Decomposition Date:** 2026-02-11
**Project Lead:** project-lead-novotechno
**Total Tasks:** 14 across 6 agents
**Estimated Duration:** 22.5 hours

---

## Phase 1: OAuth & Security Foundation (5.5 hours)

### Owner: operations-agent-novotechno (OAuth/MSAL Specialist)

#### TASK_OAUTH_001: MSAL Device Code Flow with Token Caching
**Duration:** 2.5 hours | **Priority:** P0 | **Dependencies:** TASK_001

**Scope:**
- `src/auth/device_code_flow.py` (150-200 lines)
  - PublicClientApplication configuration
  - Device code acquisition and polling (5s intervals)
  - Token response handling
  - Error handling (expired_token, authorization_declined)
- `src/auth/token_cache.py` (250 lines)
  - macOS Keychain integration (msal.KeychainPersistence)
  - Token bucket algorithm (1000 tokens, 1 token/sec refill)
  - Encrypted file fallback (`~/.openclaw/credentials/outlook/token_cache.bin`, 0600 perms)
  - Exponential backoff on Graph API 429
- Unit tests for device code flow and token bucket

**Critical Conditions:** C-001 (device code flow), C-002 (token bucket)

**Success Criteria:**
- Device code acquired successfully
- Token stored in Keychain with proper ACLs
- Token bucket enforces 20/cycle, 100/day limits
- Token survives process restart

---

#### TASK_OAUTH_002: Graph API Email Client
**Duration:** 3 hours | **Priority:** P0 | **Dependencies:** TASK_OAUTH_001

**Scope:**
- `src/auth/token_validator.py` (200 lines)
  - Pre-send validation: check token expiry >300s
  - Silent refresh logic (3 attempts → DEGRADED mode)
  - Audit logging (old_tid, new_tid, timestamp)
  - DEGRADED mode notification to Caine
- `src/collections/email_sender.py` (400 lines)
  - Graph API: POST /users/me/sendMail
  - Token bucket enforcement
  - Jinja2 template rendering
  - Error handling (429, 401, 403)
- `scripts/setup_oauth.py` (150 lines)
  - Interactive setup for first-time OAuth
  - Device code flow execution
  - Token caching + test email
- Unit tests for token refresh and email sending

**Critical Conditions:** C-006 (token refresh monitoring)

**Success Criteria:**
- Token expiry checked before each API call
- Automatic refresh succeeds before expiry
- DEGRADED mode triggers after 3 failures
- Email sends successfully via Graph API

---

## Phase 2: PDF Parsing & State Management (3.5 hours)

### Owner: python-cli-dev-novotechno

#### TASK_PDF_001: PDF Invoice Parser with Confidence Scoring
**Duration:** 2 hours | **Priority:** P0 | **Dependencies:** TASK_001

**Scope:**
- `src/collections/pdf_parser.py` (300 lines)
  - pdfplumber extraction for invoice fields:
    - invoice_number (30% weight in confidence)
    - client_name
    - amount (30% weight)
    - due_date (25% weight)
    - items[] (15% weight)
  - Confidence scoring:
    - Exact regex match: 1.0
    - Fuzzy match (90%): 0.95
    - Date parsing: 0.9
    - Currency parsing: 0.92
    - Overall confidence = weighted average
  - Routing logic: >0.95 auto-process, 0.85-0.94 review queue, <0.85 manual
- Unit tests with mock PDFs

**Critical Conditions:** C-009 (confidence >0.9)

**Success Criteria:**
- >90% fields extracted correctly from 5 test invoices
- Confidence scores accurate (0.0-1.0 range)
- Manual review queue manageable (<10% of invoices)

---

#### TASK_PDF_002: Atomic State File Writes
**Duration:** 1.5 hours | **Priority:** P0 | **Dependencies:** TASK_PDF_001

**Scope:**
- `src/state/invoice_state.py` (250 lines)
  - Atomic write pattern: `.tmp` → `os.replace()`
  - Checksum comments: `<!-- checksum:sha256:abc123 -->`
  - Append-only event log: `state/invoices/{client}/{invoice}_events.log`
  - Methods: `create()`, `update()`, `get()`, `mark_paid()`
- `src/state/ledger.py` (200 lines)
  - QMD format ledger: `state/collections_ledger.md`
  - Sections: `## Unpaid`, `## Paid`, `## Escalated`
  - Hourly reconciliation: sum(state amounts) == ledger total
- Unit tests for atomic writes and ledger

**Critical Conditions:** C-005 (atomic writes)

**Success Criteria:**
- No partial file writes after kill -9
- Checksum verifies file integrity
- Event log append-only
- Reconciliation passes

---

## Phase 3: CLI Tools (6.5 hours)

### Owner: python-cli-dev-novotechno

#### TASK_CLI_001: collections-emailer CLI
**Duration:** 3 hours | **Priority:** P0 | **Dependencies:** TASK_OAUTH_002, TASK_PDF_002

**Scope:**
- `src/collections/scheduler.py` (300 lines)
  - Email schedule rules:
    - reminder_1: T-3d before due_date
    - reminder_2: due_date
    - overdue_1: T+5d
    - overdue_2: T+7d
    - final_notice: T+10d
    - escalation: T+14d → notify account_manager
  - Respect state.paused (opt-out)
  - Batch sends if >20 emails
- `src/collections/reply_monitor.py` (250 lines)
  - Inbox scan: GET /me/messages for replies
  - Parse "Re: Recordatorio de Factura #{number}"
  - Detect keywords: STOP, PAGADO, DUDAS
  - Actions: paused=true, manual review, escalate
- `src/collections/invoice_scanner.py` (200 lines)
  - Watch invoices/{client}/ folders (initial scan)
  - Parse PDFs → create state files
  - Deduplication via checksum
- `scripts/collections-emailer.py` (100 lines) — CLI entry point
  - Click decorators
  - Heartbeat wrapper: caffeinate -i -s (C-004)
  - Signal handlers: SIGTERM → graceful shutdown

**Critical Conditions:** C-004 (sleep/wake robustness)

**Success Criteria:**
- Emails sent on correct schedule
- Rate limiting enforced (20/cycle)
- Reply detection works
- Graceful shutdown on SIGTERM

---

#### TASK_CLI_002: payment-watcher CLI
**Duration:** 2 hours | **Priority:** P0 | **Dependencies:** TASK_PDF_002

**Scope:**
- `src/filesystem/payment_detector.py` (250 lines)
  - watchdog.Observer for real-time monitoring
  - FileSystemEventHandler for `.pdf.tmp` → `.pdf` moves
  - Payment confidence check: verify amount matches invoice
  - Update state: status='paid', paid_date=now()
  - Move to archive: `state/archive/{client}/`
- `src/filesystem/message_sender.py` (150 lines)
  - Send INVOICE_PAID:{number}:{slug} to collections-emailer
  - JSON format with deduplication (24h window)
  - File-based fallback if sessions_send fails
- `scripts/payment-watcher.py` (100 lines)
  - Click CLI, heartbeat wrapper, signal handlers

**Critical Conditions:** C-003 (fsevents <30s latency)

**Success Criteria:**
- Payment detection latency <30s
- State updated correctly
- Archive move successful
- Inter-agent message sent

---

#### TASK_CLI_003: collections-supervisor CLI
**Duration:** 1.5 hours | **Priority:** P1 | **Dependencies:** TASK_CLI_001, TASK_CLI_002

**Scope:**
- `src/supervisor/health_checker.py` (200 lines)
  - Hourly health checks for both agents
  - Parse last-run timestamps from logs
  - State consistency validation (ledger vs state files)
  - Escalate to Caine after 2 missed heartbeats
- `src/supervisor/dashboard.py` (150 lines)
  - Generate HTML dashboard: unpaid/paid/escalated counts
  - Payment velocity metrics
  - Error rate tracking
- `scripts/collections-supervisor.py` (100 lines)
  - Click CLI with --health-check and --dashboard modes

**Success Criteria:**
- Health check detects missed heartbeats
- Dashboard shows accurate metrics
- Escalation triggers correctly

---

## Phase 4: QA Validation (6 hours)

### Owner: qa-engineer-novotechno

#### TASK_QA_001: OAuth Token Persistence Validation (C-008)
**Duration:** 2.5 hours | **Priority:** P0 | **Dependencies:** TASK_OAUTH_002

**Scope:**
- `tests/test_oauth_persistence.py` (100 lines)
- Run 2-hour continuous validation:
  - Setup OAuth → cache token
  - Restart agent process every 30 minutes (4 restarts)
  - Verify token reuse without re-auth each time
  - Mock token expiry → verify automatic refresh
- Document results in `~/.openclaw/workspace-qa-engineer-novotechno/OAUTH-VALIDATION-RESULTS.md`

**Critical Conditions:** C-008 (2-hour validation)

**Success Criteria:**
- Token reused across 3+ restarts without re-auth
- Silent refresh succeeds before expiry
- No manual intervention required
- **Gate:** Upgrades confidence from Substantive → Definitive

---

#### TASK_QA_002: PDF Parsing Confidence Validation (C-009)
**Duration:** 1.5 hours | **Priority:** P0 | **Dependencies:** TASK_PDF_001

**Scope:**
- `tests/test_pdf_confidence.py` (120 lines)
- Parse 5 diverse invoice templates
- Measure field extraction accuracy
- Verify confidence algorithm
- Report: accuracy %, confidence distribution, review queue size

**Critical Conditions:** C-009 (>0.9 threshold)

**Success Criteria:**
- >90% fields extracted correctly
- Confidence algorithm validated
- Manual review queue <10% of invoices

---

#### TASK_QA_003: E2E Integration Testing
**Duration:** 2 hours | **Priority:** P0 | **Dependencies:** TASK_CLI_001, TASK_CLI_002, TASK_CLI_003

**Scope:**
- Full payment cycle test:
  1. Drop PDF in invoices/{client}/
  2. Verify state file created with correct data
  3. Wait for reminder email (T-3d)
  4. Simulate payment: move .pdf to paid/
  5. Verify state updated to 'paid'
  6. Verify archive move
  6. Verify supervisor dashboard updated
- Test error scenarios: OAuth failure, PDF parse error, filesystem permission denied

**Success Criteria:**
- E2E cycle completes without manual intervention
- All error scenarios handled gracefully
- State consistency maintained throughout

---

## Phase 5: Documentation (1 hour)

### Owner: scribe-novotechno

#### TASK_DOCS_001: OAuth Setup Runbook
**Duration:** 1 hour | **Priority:** P1 | **Dependencies:** TASK_OAUTH_001, TASK_OAUTH_002

**Scope:**
- `docs/oauth-setup.md` (comprehensive runbook)
  - Microsoft Graph API permission requirements
  - Azure AD app registration steps
  - Device code flow explanation
  - Token caching architecture
  - Troubleshooting guide
- Update `DECISIONS.md` with OAuth security decisions

**Success Criteria:**
- Runbook enables independent OAuth setup
- Security decisions documented
- Troubleshooting section covers common issues

---

## Phase 6: Release (0.5 hours)

### Owner: git-commit-agent-novotechno

#### TASK_GIT_001: GitHub v1.0.0 Release
**Duration:** 30 minutes | **Priority:** P1 | **Dependencies:** TASK_QA_001, TASK_QA_002, TASK_QA_003

**Scope:**
- Tag: `v1.0.0` (annotated tag with release notes)
- Release notes: features, bug fixes, known limitations
- GitHub release with binary artifacts
- Update README.md with setup instructions

**Success Criteria:**
- Tag pushed to GitHub
- Release created with notes
- README updated
- All 4 production gates signed off

---

## Agent Workload Distribution

| Agent | Tasks | Estimated Hours | Critical Tasks |
|-------|-------|-----------------|----------------|
| operations-agent-novotechno | 2 | 5.5 | 2 (OAuth) |
| python-cli-dev-novotechno | 5 | 9.5 | 4 (PDF + CLI) |
| qa-engineer-novotechno | 3 | 6.0 | 3 (all validation) |
| scribe-novotechno | 1 | 1.0 | 0 |
| git-commit-agent-novotechno | 1 | 0.5 | 0 |
| project-lead-novotechno | 1 | 0.5 | 1 (decomposition) |

**Total:** 14 tasks, 22.5 hours

---

## Critical Path Analysis

**Longest path:** TASK_001 → TASK_OAUTH_001 → TASK_OAUTH_002 → TASK_CLI_001 → TASK_QA_003 → TASK_GIT_001
**Duration:** 0.5 + 2.5 + 3 + 3 + 2 + 0.5 = **11.5 hours**

**Parallel work:**
- TASK_PDF_001 & TASK_PDF_002 can run parallel to OAuth (saves 3.5h)
- TASK_CLI_002 can run parallel to TASK_CLI_001 (saves 2h)
- TASK_DOCS_001 can run parallel to later tasks (saves 1h)

**Optimized timeline:** ~11.5 hours (critical path) + 1 hour (docs) = **12.5 hours**

---

## Pattern Extraction Opportunities

1. **PAT-065: Agent Heartbeat Protocol** (from supervisor health checks)
2. **PAT-066: Event-Driven Agent Coordination** (from INVOICE_PAID messages)
3. **PAT-067: Confidence-Based Validation Pipeline** (from PDF scoring)

These will be validated during execution and extracted during ABSORPTION phase.
