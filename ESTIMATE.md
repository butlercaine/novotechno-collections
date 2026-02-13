ESTIMATE START
PROJECT: PROJ-2026-0210-novotechno-collections | DATE: 2026-02-11 | CALIBRATION: 6 projects

| Dimension | Estimate | Confidence | Basis |
|-----------|----------|------------|-------|
| Task Count | 12 | M | Complexity 4/5 with 3 CLI agents + shared infra exceeds CreditWatch's 8 tasks but below echo-calculator's 22. 3 distinct agents require dev+integration cycles; shared PDF/OAuth components add cross-cutting tasks. No direct Operations domain precedent. |
| Agent Count | 7 | H | Brief explicitly requires 3 CLI agents + mandatory 4 (lead, QA, scribe, commit). Pattern consistent across high-complexity projects (avg 6.5 agents). |
| Rework Rate | 20% | M | Multi-agent coordination risk for 3 interacting agents (API drift, state sync). Echo-calculator's 55% rework was cross-domain; CreditWatch's 5% was single-agent. Operations domain lacks data; middle-range estimate accounts for OAuth/PDF parsing uncertainty. |

METHODOLOGY: Pattern matching against high-complexity Engineering projects (CreditWatch: 8 tasks/6 agents/5% rework, echo-calculator: 22 tasks/7 agents/55% rework) adjusted for Operations domain novelty and explicit 3-agent architecture. Task count derived from agent interaction surface and external integration burden.
RISKS: (1) OAuth/MSAL device flow + macOS Keychain integration untested in calibration data; potential silent failures. (2) Atomic state writes across 3 agents risks race conditions and phantom reads if file locking semantics mis-specified.
ESTIMATE END
