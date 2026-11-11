# Phase 6.1 — Implementation Report

**Date:** 2026-11-10  
**Baseline:** 214 passed / 0 failed / 0 skipped  
**Final:** **233 passed / 0 failed / 0 skipped**  
**pip check:** clean  
**No commit / no push.** Existing uncommitted work preserved.

---

## A. Verdict

**COMPLETE**

Principal-scoped L2 authorization and build process-group lifecycle hardening are implemented, tested (including real subprocess fixtures), and regression-green.

---

## B. Repository audit findings

### Original L2 authorization

- `MAX_GRANTABLE = L2` capped claims but did not bind L2 to a trusted principal.
- `CallContext.principal` / `max_level` were caller-supplied strings.
- **Escalation path:** `AgentBrokerSession(max_level="L2", allowed_tools=["west_build"])` or any `BrokerClient.call(..., principal="engineering_os", max_level="L2")` could invoke L2.

### Original west_build lifecycle

- `subprocess.run(..., timeout=T)` without a process group.
- On timeout, descendants (cmake/ninja/compiler) could survive after the parent exited.

---

## C. Implementation changes

| File | Change |
|---|---|
| `device_broker/permissions.py` | `ENGINEERING_OS_L2_TOOLS`, `ENGINEERING_OS_PRINCIPAL` |
| `device_broker/types.py` | `CallContext.session_id` |
| `device_broker/client.py` | Session-bound client defaults |
| `device_broker/broker.py` | `BrokerSession`, `create_client`, `create_engineering_client`, L2 session gate, workspace build locks |
| `device_broker/process_exec.py` | **New** — process-group run + SIGTERM/SIGKILL cleanup |
| `device_broker/tools/build_tools.py` | Uses `process_exec`; per-source-dir build lock |
| `master/broker_service.py` | Untrusted shared client + trusted eng client |
| `master/engineering_service.py` | Binds Engineering OS to trusted eng client |
| `tests/device_broker/test_phase61_auth.py` | **New** authorization tests |
| `tests/device_broker/test_phase61_process.py` | **New** real subprocess lifecycle tests |
| Phase 6 tests | Updated to use `create_engineering_client()` |
| `docs/implementation/PHASE6_1_PLAN.md` | Plan |
| `docs/implementation/PHASE6_1_IMPLEMENTATION_REPORT.md` | This report |

### Authorization model (actual)

```text
L2 tool invoke requires:
  1. required <= MAX_GRANTABLE (L2; L3 blocked)
  2. Valid Broker-issued session_id
  3. tool ∈ session.l2_tools
  4. claimed max_level (capped by session.max_level) >= required
```

Engineering OS session grants only `{west_build, serial_capture_passive}`.

### Build lifecycle (actual)

- `start_new_session=True` (new PGID).
- Timeout → SIGTERM process group → bounded grace → **always** SIGKILL process group (even if main already exited) → reap.
- Streaming stdout/stderr with byte caps.
- Per-resolved-`source_dir` `threading.Lock` serializes concurrent builds in the same workspace.

---

## D. Authorization results

| Test case | Expected | Actual | Result |
|---|---|---|---|
| ResearchAgent L2 | Denied | Denied; backend not called | PASS |
| Generic agent L2 | Denied | Denied | PASS |
| Allowlist escalation | Denied | Denied | PASS |
| Principal spoofing | Denied | Denied (no session) | PASS |
| Forged session_id | Denied | Denied | PASS |
| Engineering OS west_build | Allowed | Allowed | PASS |
| Engineering OS passive capture | Allowed | Allowed | PASS |
| Unapproved L2 tool | Denied | Denied; backend not called | PASS |
| L3 operation | Denied | Denied | PASS |
| L0/L1 untrusted | Allowed | Allowed | PASS |

---

## E. Process lifecycle results

| Case | Evidence type | Result |
|---|---|---|
| Successful fixture | Real subprocess | PASS |
| Failed exit 7 | Real subprocess | PASS |
| Timeout + reap | Real subprocess | PASS |
| SIGTERM-ignoring child → SIGKILL group | Real subprocess + `/proc` scan | PASS |
| Output size limit | Real subprocess | PASS |
| Partial output on timeout | Real subprocess | PASS |
| west_build timeout termination metadata | Broker + fixture runner | PASS |
| Concurrent builds serialized | Mocked runner + lock | PASS (max concurrency 1 per workspace) |

---

## F. Test results

| Suite | Passed | Failed | Skipped |
|---|---:|---:|---:|
| Phase 6.1 authorization | 11 | 0 | 0 |
| Phase 6.1 process lifecycle | 8 | 0 | 0 |
| Full regression (all listed suites) | **233** | **0** | **0** |

Commands:

```bash
cd ~/pyra
agent-os/.venv/bin/pip check
PYDANTIC_AI_NO_BANNER=1 agent-os/.venv/bin/python -m pytest \
  tests/agent_runtime tests/master tests/project_os tests/device_broker \
  tests/engineering_os tests/model_gateway tests/research_agent -q
```

Baseline comparison: 214 → 233 (+19).

---

## G. Remaining restrictions

1. Session tokens are in-process only (sufficient for PYRA’s in-process BrokerClient model; not a network auth system).
2. Workspace build lock is in-process threading lock — not cross-process/host-wide.
3. Process-group kill requires permission to signal the group (normal for locally spawned builds).
4. No hardware validation in 6.1.
5. L3 / flash / UART TX remain unavailable.

---

## H. Phase 7 readiness

| Prerequisite | Status |
|---|---|
| Principal-scoped L2 authorization | Satisfied |
| Broker-enforced authorization | Satisfied |
| Build-process cleanup | Satisfied (real subprocess evidence) |
| Audit integrity | Satisfied (denials audited; no secrets added) |
| Regression stability | Satisfied (233 pass) |

Phase 7 may proceed to design human-approved L3 — not implemented here.
