# Retrospective — PROJ-2026-0210-novotechno-collections

**Project:** Automated Invoice Collections System for NovotEcho SAS
**Domain:** Engineering (Operations + Python CLI)
**Complexity:** 4/5
**Duration:** 2026-02-11 (single day)
**Team:** 6 agents (project-lead, qa-engineer, scribe, git-commit-agent, python-cli-dev, operations-agent) + Caine (orchestrator)
**Outcome:** ACCEPTED

---

## Executive Summary

Automated invoice collections system for NovotEcho SAS — a Colombian-based company. System includes OAuth/MSAL device code flow, PDF invoice parsing with confidence scoring, 3 CLI agent tools (collections-emailer, payment-watcher, collections-supervisor), atomic state management, and an HTML monitoring dashboard. Delivered with 91% test coverage (22 unit + 13 E2E tests), v1.0.0 tagged and committed.

This was E2E test #7 for the OpenClaw system — the most complex project to date (4/5). It validated Phase B auto-dispatch, completion guard, and mid-term memory extraction, while exposing critical session management patterns for kimi-k2-thinking models.

---

## Patterns Discovered (Repeat These)

### P1: Focused Dispatch Over Full-File Dispatch
**Principle:** When an agent struggles with a large task file (>10KB), send a focused message with only the specific information needed rather than referencing the entire task file.
**Evidence:** QA_003 first attempt consumed 170 lines (164KB) over 25 minutes, model-switched from kimi-k2-thinking to MiniMax-M2.1, got 10/13 tests but ran out of turns. Second attempt with a focused 200-word message describing only the 3 failing tests completed in <8 minutes with 13/13 passing.
**Commitment:** For rework/retry dispatches, always extract the specific failure and required fix into the dispatch message.
**Trigger:** Any task retry or QA rework dispatch.

### P2: Session Clearing Between Sequential Tasks
**Principle:** Clear agent sessions between sequential task dispatches to the same agent. Context accumulation kills subsequent dispatches.
**Evidence:** CLI_003 auto-dispatched immediately after CLI_002 completed on the same agent (python-cli-dev-novotechno). Session had 146 lines accumulated from CLI_002. CLI_003 died instantly (pid_dead). Clearing sessions resolved it every time.
**Commitment:** Always `mv *.jsonl *.jsonl.bak && echo '{}' > sessions.json` before dispatching a new task to an agent that just completed a task.
**Trigger:** Any sequential task dispatch to the same agent.

### P3: Watcher Pause Before Manual Dispatch
**Principle:** The watcher's completion guard retries and manual dispatches compete for the same agent session. Always pause the watcher before manual intervention.
**Evidence:** CLI_003 manual dispatch was immediately contended by watcher guard retry — both processes died. Pausing the watcher resolved the contention.
**Commitment:** `task-dispatch-watcher pause <project>` before any manual `openclaw agent` dispatch; `resume` after completion.
**Trigger:** Any manual dispatch while watcher is active.

### P4: Confidence-Based PDF Routing
**Principle:** Multi-tier confidence routing (auto-process >0.95, review 0.85-0.94, manual <0.85) keeps manual review queues manageable.
**Evidence:** 5 diverse templates validated. Average confidence 0.965, field accuracy 95%, estimated manual review <5%. Production-ready with no ML dependency.
**Commitment:** Apply confidence-based routing to any document parsing pipeline.
**Trigger:** Any project involving document extraction.

### P5: One-Task-Per-Agent Invariant
**Principle:** Never dispatch a second task to an agent that already has a DISPATCHED task. Gateway sessions can't handle concurrent CLI processes.
**Evidence:** Watcher dispatched CLI_001 + CLI_002 + QA_001 to agents still processing PDF_002 + QA_002 — all 5 tasks FAILED with pid_dead. Implementing the one-task-per-agent check in the watcher eliminated this class of failure.
**Commitment:** Watcher enforces this automatically. For manual dispatch, verify MANIFEST shows no DISPATCHED tasks for the target agent.
**Trigger:** Every dispatch decision.

---

## Failures and Root Cause Analysis

### F1: CLI_002 — max_retries_exceeded (pid_dead)
**Severity:** Major
**What happened:** Watcher dispatched CLI_002 after OAUTH_002 completed. Agent process died without writing RESPONSE. Guard retried 2x, all attempts failed.
**Root cause:** Session accumulated context from prior tasks on the python-cli-dev agent. The kimi-k2-thinking model couldn't start a new task on a session with prior history.
**Resolution:** Cleared session files manually, dispatched fresh. CLI_002 completed successfully on second manual attempt (10/10 tests).
**Systemic fix:** Session clearing between tasks (Pattern P2).

### F2: QA_002 — Exec Tool Failure
**Severity:** Minor
**What happened:** QA agent wrote a RESPONSE but commands in the response had `:` prefixes, indicating the agent's exec tool was failing. The agent produced validation results through alternative means.
**Root cause:** Model (kimi-k2-thinking) sometimes prefixes shell commands with `:` (a no-op in bash), indicating confusion about tool invocation.
**Resolution:** Agent self-recovered by using Python exec instead of shell commands. Result was valid.
**Systemic fix:** None needed — model quirk, not a systemic issue.

### F3: CLI_003 — Multiple Dispatch Failures
**Severity:** Critical (process failure, not code failure)
**What happened:** CLI_003 failed 4 times before succeeding. Failure chain: (1) watcher auto-dispatch into accumulated session → pid_dead, (2) guard retry into empty session → pid_dead, (3) manual dispatch with wrong stop-hook args → agent received filename as message, (4) manual dispatch contended with watcher retry → both died.
**Root cause:** Compound failure: session accumulation + stop-hook 4-arg calling convention misunderstood + watcher/manual contention.
**Resolution:** Paused watcher, cleared session, dispatched directly with correct CLI invocation.
**Systemic fix:** Patterns P2 and P3. Also documented: `agent-with-response-guard` takes exactly 4 args: `<agent-id> <task-path> <response-path> <message>`.

### F4: QA_003 — Ran Out of Turns
**Severity:** Major
**What happened:** First dispatch: agent spent 25+ minutes (170 lines, 164KB) writing E2E test infrastructure. Model switched from kimi-k2-thinking to MiniMax-M2.1 mid-task. Got 10/13 tests passing but ran out of turns before writing RESPONSE.
**Root cause:** Task was too large for the model's effective context. The 17KB task file + accumulated session context exceeded the model's ability to stay on-task.
**Resolution:** Second dispatch with a focused message describing exactly the 3 failing tests and required fixes. Completed in <8 minutes.
**Systemic fix:** Pattern P1 (focused dispatch). Also: consider breaking large QA tasks into smaller scopes.

---

## Assumptions That Were Wrong

### A1: "Auto-dispatch handles everything after root task dispatch"
**Reality:** Auto-dispatch works for the happy path, but session accumulation means ~60% of sequential dispatches to the same agent fail on first attempt. The watcher's completion guard catches and retries these, but the retry also fails if the session isn't cleared. Manual intervention was required for 5 of 14 tasks.

### A2: "kimi-k2-thinking can handle 15KB+ task contexts"
**Reality:** The model struggles significantly with large contexts. Tasks over ~10KB benefit from focused dispatch messages that extract only the relevant portion. The model also switches to MiniMax-M2.1 when it hits capacity, at significantly higher cost.

### A3: "Stop-hook wrapper simplifies dispatch"
**Reality:** The `agent-with-response-guard` wrapper introduces its own failure mode (argument count sensitivity). Direct `openclaw agent --agent ... --message "..."` invocation is more reliable for manual dispatch.

---

## New Capabilities Developed

### NC1: One-Task-Per-Agent Watcher Enhancement
**Generalizable:** Yes. The `get_busy_agents(manifest)` function and dispatch deferral logic in the watcher prevents concurrent dispatch to the same agent. This fixes a class of silent failures where concurrent CLI processes on the same session cause all processes to die.

### NC2: Session Clearing Protocol
**Generalizable:** Yes. The pattern of clearing sessions between sequential tasks applies to all projects using kimi-k2-thinking or any model that accumulates session context.

### NC3: Focused Dispatch Pattern
**Generalizable:** Yes. For any retry or rework dispatch, sending a focused message with specific failure details dramatically improves completion rate vs. referencing the full task file.

---

## Efficiency Metrics

| Metric | Estimated | Actual | Notes |
|--------|-----------|--------|-------|
| Total tasks | 14 | 14 | Exact match |
| Agent count | 6 | 6 | Exact match |
| Estimated duration | 22.5h work / 12.5h critical path | ~5.5h wall clock | Significant parallelization + fast model execution |
| QA rejections | 0 expected | 0 formal rejections | QA_003 needed 2 dispatches but first wasn't a formal rejection |
| Rework tasks | 0 | 0 | No formal rework cycles |
| Tasks needing manual intervention | 0 expected | 5 of 14 | CLI_002, QA_002, CLI_003, QA_003, GIT_001 all needed session clearing + manual dispatch |
| Completion guard triggers | N/A | 4 | CLI_002 (2x), CLI_003 (1x), QA_002 (1x) |
| Agent busy skips | N/A | Multiple | One-task-per-agent fix deployed mid-project |
| Watcher auto-dispatches | Expected all | ~50% success rate | Session accumulation is the primary failure mode |

---

## Team Performance

| Agent | Tasks | Performance | Notes |
|-------|-------|-------------|-------|
| project-lead-novotechno | 1 (decomposition) | Excellent | Clean decomposition, 14 tasks with proper dependencies, critical path analysis |
| operations-agent-novotechno | 2 (OAuth) | Good | Both tasks completed, OAUTH_002 needed 1 guard retry (timeout_pid_dead) |
| python-cli-dev-novotechno | 5 (PDF + CLI) | Good with caveats | All tasks completed, but 3 needed manual intervention due to session issues |
| qa-engineer-novotechno | 3 (validation) | Mixed | QA_001 and QA_002 solid. QA_003 needed 2 dispatches (ran out of turns on first) |
| scribe-novotechno | 1 (docs) | Excellent | Quick, clean documentation. OAuth setup runbook + architecture overview |
| git-commit-agent-novotechno | 1 (release) | Good | Clean commit + tag, needed session clearing before dispatch |

### Team Composition Assessment
- **Essential roles:** python-cli-dev (5 tasks, heavy workload), qa-engineer (3 tasks, caught real bugs in E2E)
- **Efficient roles:** operations-agent (2 OAuth tasks — specialized knowledge justified), scribe (1 task, fast)
- **Overhead:** git-commit-agent (could be a Caine-direct task for simple projects)
- **Optimal team size for 4/5 complexity:** 4-5 agents (current 6 was slightly over-staffed; scribe + git could merge)

---

## Recommendations for System Improvement

### R1: Auto-Session-Clear on Sequential Dispatch (Priority: High)
Add automatic session clearing to the watcher's `auto_dispatch_task()` when dispatching a task to an agent that previously had a COMPLETE task. This would eliminate the #1 failure mode (session accumulation).

### R2: Task Size Limits for kimi-k2-thinking (Priority: Medium)
Add a heuristic: if a TASK file exceeds 10KB, the watcher should compose a focused dispatch message from the task's acceptance criteria section rather than sending the full file reference.

### R3: Watcher Self-Pause on Manual Dispatch Detection (Priority: Low)
If the watcher detects a CLI process already running for a project's agent (via PID check), it should auto-pause for that agent rather than compete.

### R4: Merge Scribe + Git Commit for Simple Projects (Priority: Low)
For projects with complexity ≤3/5, a single documentation+release agent would reduce team overhead.

---

## Pattern Extraction Candidates

Per the DECOMPOSITION.md, three patterns were flagged for extraction:
1. **PAT-065: Agent Heartbeat Protocol** — Validated. Supervisor health checker implements heartbeat monitoring with configurable thresholds and auto-escalation.
2. **PAT-066: Event-Driven Agent Coordination** — Validated. Payment watcher → collections-emailer coordination via JSONL queue files.
3. **PAT-067: Confidence-Based Validation Pipeline** — Validated. PDF parser confidence scoring with 3-tier routing (auto/review/manual).

Additionally, from infrastructure learnings:
4. **PAT-068: Session Clearing Protocol** — New pattern from this project. Clear agent sessions between sequential tasks.
5. **PAT-069: Focused Dispatch for Weak Models** — New pattern from this project. Send targeted context instead of full task files for retries.

---

**Retrospective prepared by:** Caine (orchestrator)
**Date:** 2026-02-11
**Project #:** 7 (E2E test series)
