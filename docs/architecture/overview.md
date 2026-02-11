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
