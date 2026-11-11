# Phase 6.1 — Implementation Plan

**Baseline:** 214 passed / 0 failed / 0 skipped; `pip check` clean.

## Current authorization flow

1. Caller builds `CallContext(principal, max_level, client, project_id)` — all caller-supplied.
2. Broker caps `max_level` at `MAX_GRANTABLE=L2`.
3. `level_allowed(required, max_level)` only compares integers.
4. **Gap:** Any caller that sets `max_level=L2` and knows the tool name can invoke L2 (including spoofed `principal="engineering_os"`). Allowlists are only checked in AgentBrokerSession, not Broker.

## Escalation path

`AgentBrokerSession(max_level="L2", allowed_tools=["west_build"]).call("west_build", …)` → BrokerClient → invoke with max_level L2 → **allowed today**.

## Proposed principal isolation

- `DeviceBroker.create_client(...)` issues an opaque `session_id` registered on the broker with principal, max_level, and explicit `l2_tools`.
- `BrokerClient.call` always attaches its `session_id`.
- For tools with `required >= L2`, Broker requires a valid session whose `l2_tools` contains the tool; principal string alone is insufficient.
- Engineering OS uses a trusted client (`west_build`, `serial_capture_passive` only).
- Shared Master/agent clients remain untrusted (no L2 tools).

## Current west_build lifecycle

`subprocess.run(..., timeout=T)` without process group. On timeout, parent may die while cmake/ninja/gcc descendants continue.

## Proposed lifecycle

- `start_new_session=True` (new process group).
- On timeout: SIGTERM to group → bounded grace → SIGKILL to group → reap.
- Bounded output via PIPE + size caps.
- Per-workspace threading lock for concurrent builds.

## Files

- `device_broker/permissions.py` — principal policy helpers
- `device_broker/types.py` — session_id on CallContext
- `device_broker/broker.py` — session registry + L2 gate
- `device_broker/client.py` — trusted client construction
- `device_broker/tools/build_tools.py` — process group runner + lock
- `device_broker/process_exec.py` — shared process-group executor (new)
- `master/engineering_service.py` / `broker_service.py` — wire trusted eng client
- Tests + `PHASE6_1_IMPLEMENTATION_REPORT.md`
