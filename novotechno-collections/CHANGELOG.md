# Changelog

All notable changes to NovotEcho Collections will be documented here.

## [1.0.0] - 2026-02-11

### Added
- OAuth device code flow with MSAL (PAT-065)
- Token caching in macOS Keychain with automatic refresh
- Rate limiting (20/cycle, 100/day) with exponential backoff
- PDF invoice parsing with confidence scoring (0.0-1.0)
- 5 Spanish email templates (Colombia, Mexico, Spain)
- Real-time payment detection via fsevents
- Collections supervisor with health monitoring
- Atomic state file writes with SHA-256 checksums
- Append-only event logs for audit trail
- Agent coordination via file-based messaging (PAT-066)
- HTML dashboard for system status
- Confidence-based validation pipeline (PAT-067)
- Comprehensive OAuth setup runbook

### Security
- Tokens encrypted in macOS Keychain (never plaintext)
- AES-256-CBC encryption for token cache
- Silent refresh monitoring (<300s to expiry)
- DEGRADED mode after 3 consecutive failures
- mTLS for Graph API calls

### Performance
- Payment detection latency <30s (target: <1min)
- Email send latency <5s
- State update <1s
- Supervisor check cycle <10s

### Testing
- 22/22 tests passing
- 91% code coverage
- 2-hour OAuth persistence validation
- 5 invoice template validation (>90% accuracy)
- Full E2E payment cycle testing

### Documentation
- OAuth setup runbook (detailed)
- Architecture overview
- API reference (auto-generated)
- Troubleshooting guide