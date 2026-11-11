# Phase 7 — Plan

**Baseline:** 233 passed; `pip check` clean.  
**Hardware at audit:** USB Arduino `2341:0043`; audio device; no `/dev/ttyACM*`; no `west`/`arm-none-eabi-gcc`/`avrdude`; `openocd` present.  
**Constraint:** Preserve frozen architecture; no commit/push; keep Phase 6.1 session isolation.

## Gaps

| Area | Gap |
|---|---|
| Specialists | Only echo/broker_probe/research |
| Orchestration | Single-handler; no multi-agent workflow |
| Project OS | No first-class plan/requirements/architecture store |
| L3 | MAX_GRANTABLE=L2; no approval tokens; flash denied |
| Master confirm | `NeedsConfirm` unused |
| Mark→full workflow | Bring-up stops at L2 build |

## Implementation sequence

1. Specialist contracts (`engineering_contracts.py`)
2. Project OS engineering artifact helpers (JSON under `artifacts/engineering/`)
3. Seven specialists (PydanticAI + deterministic synthesize for tests)
4. Master `engineering_workflow` orchestrator (dependency-ordered Agent Runtime invocations)
5. Broker approval tokens + L3 `program_firmware` / `erase_flash` (session + approval gated)
6. Engineering OS flash/verify stages
7. Wire HARDWARE_BRINGUP / new engineering intent → full workflow; `needs_confirm` for L3
8. Tests + conformance docs
9. Live demo attempt (honest about hardware/toolchain limits)

## Security invariants (unchanged)

- Agents never get L3 sessions.
- Programming requires Broker-minted, operation-bound, single-use, expiring approval.
- Generic principal spoofing cannot obtain Eng OS session.
- Build ≠ flash ≠ verified.

## Expected verdict

Likely **COMPLETE WITH DOCUMENTED RESTRICTIONS** if physical program/verify cannot run on this host (missing programmer toolchain / no serial ACM). Architecture + automated e2e must still be demonstrated.

## Status

Implemented. See `PHASE7_IMPLEMENTATION_REPORT.md` and `PHASE7_ARCHITECTURE_CONFORMANCE.md`.

**Final verdict:** `COMPLETE WITH DOCUMENTED RESTRICTIONS`  
**Tests:** 252 passed; `pip check` clean.
