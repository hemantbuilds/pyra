# Phase 6 — Implementation Report (Engineering OS L2 Execution)

**Date:** 2026-11-10  
**Verdict target:** COMPLETE WITH DOCUMENTED RESTRICTIONS  
**Baseline before Phase 6:** 170 passed  
**After Phase 6:** 214 passed / 0 failed / 0 skipped  

---

## Architecture and ownership

```text
User → Mark → Dot → Master
                 → Project OS (project identity / workspace)
                 → Engineering OS (plan + orchestrate)
                      → BrokerClient
                           → Device Broker (L0 discovery / L1 FS / L2 build+serial)
                                → host resources
```

**AI proposes. Deterministic services execute. Evidence establishes results.**  
Live model tool-calling is not a safety dependency (Phase 5d.1).

---

## New modules

| Module | Role |
|---|---|
| `device_broker/tools/build_tools.py` | L2 `west_build` |
| `device_broker/tools/serial_tools.py` | L2 `serial_capture_passive` |
| `engineering_os/board_id.py` | Structured board identification |
| `engineering_os/build_env.py` | Toolchain / build-system compatibility |
| `engineering_os/firmware_prep.py` | Deterministic Zephyr blinky scaffold |
| `engineering_os/workflow.py` | Bring-up orchestration |
| `engineering_os/states.py` | `planned|running|blocked|failed|built|…` |

## Modified modules

| Module | Change |
|---|---|
| `device_broker/permissions.py` | `MAX_GRANTABLE = L2` (L3 still blocked) |
| `device_broker/broker.py` | Injectable build/serial backends; ceiling messages |
| `device_broker/policy.py` | Build/serial timeout & output limits |
| `device_broker/tools/registry.py` | Register L2 tools |
| `engineering_os/platforms/profiles.py` | `imxrt1170_evkb` + `zephyr_board` metadata |
| `engineering_os/service.py` | `bringup_build()` |
| `master/engineering_handlers.py` | `HARDWARE_BRINGUP` → L2 workflow |

---

## Discovery / board identification

- Phase 4 USB/serial/probe enumeration **extended**, not rewritten.
- New profile `imxrt1170_evkb` with validated `zephyr_board`.
- `resolve_board_identification()` returns `identified`, evidence, unknowns, candidates.
- Ambiguous close scores → not identified; clear score winner accepted.
- Development-board confidence still capped (MCU silicon not USB-confirmed).

## Toolchain / build env

- `discover_build_tools` / `assess_build_compatibility` for Zephyr & PlatformIO markers.
- Production workflow prefers Broker `get_available_toolchains` (L0).
- Never installs tools; never claims buildable from markers alone.

## Firmware prep + build

- Deterministic blinky files under `{workspace}/firmware/zephyr_blinky/` via L1 writes.
- L2 `west_build`: structured argv, board regex, path jail, controlled env allowlist, timeout/output bounds, artifact listing.
- Success = exit_code 0 (+ evidence). `flash_attempted` always false.

## Serial

- Enumerate remains L0 (no open).
- L2 `serial_capture_passive`: allowlisted `/dev` prefixes, baud enum, bounded duration/bytes, no TX.
- UART TX **not registered** (fail-closed).

## Permissions

| Principal path | Max |
|---|---|
| Engineering OS bring-up | L2 for `west_build` / `serial_capture_passive` |
| ResearchAgent / AgentBrokerSession default | Still ≤ L1 unless explicitly configured; Broker still enforces |
| Flash/erase/persist | Unregistered → denied (L3 messaging) |

---

## Operation states

`planned` → `running` → `blocked` | `failed` | `built`  
`verified` reserved for actual verification (not used for compile-only).

## Known limitations

1. UART TX unavailable by design in Phase 6.
2. Real `west` builds require an installed Zephyr environment; CI uses mocked runners.
3. Board ID remains evidence-limited (USB ≠ MCU silicon confirmation).
4. PlatformIO build execution not implemented (detection only).
5. Physical LED verification not implemented (would require flash — Phase 7).
6. No Phase 7 approval mechanism.

## Non-goals respected

No OpenRouter/LiteLLM, no L3, no commit/push, no architecture baseline redesign, no live-AI tool-calling dependency.
