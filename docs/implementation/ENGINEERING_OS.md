# Engineering OS

**Status:** Phase 4 discovery + **Phase 6 L2 bring-up build**  
**Package:** `agent-os/engineering_os/`  
**Master:** `master/engineering_service.py`, `master/engineering_handlers.py`

---

## Architecture

```text
Mark → Dot → Master → engineering_os
                         ├── discover_hardware()     (L0/L1 evidence)
                         └── bringup_build()         (L2 west build; no flash)
                                → Device Broker
```

Engineering OS never opens serial ports or runs host commands except through Device Broker.

**Principle:** AI proposes. Deterministic services execute. Evidence establishes results.

---

## Capabilities

| Capability | Status |
|---|---|
| Hardware discovery | Done (Phase 4) |
| Evidence-based board identification | Done (extended Phase 6) |
| Toolchain / Zephyr readiness | Done |
| Zephyr blinky preparation | Done (Phase 6) |
| Broker-mediated `west build` (L2) | Done (Phase 6) |
| Passive serial capture (L2) | Done (optional in workflow) |
| UART TX | **Unavailable** (Phase 6) |
| Flash / erase / persist | **Unavailable** (Phase 7) |

---

## Device Broker tools (engineering-relevant)

| Tool | Level |
|---|---|
| `enumerate_usb_devices` | L0 |
| `enumerate_serial_devices` | L0 |
| `enumerate_debug_probes` | L0 |
| `get_available_toolchains` | L0 |
| `write_text_file` / `create_directory` | L1 |
| `west_build` | L2 |
| `serial_capture_passive` | L2 |

Grantable ceiling: **L2**. L3 remains denied.

**Phase 6.1:** Engineering OS uses a Broker-issued trusted session
(`DeviceBroker.create_engineering_client()`). L2 tools are granted only via that
session’s explicit allowlist (`west_build`, `serial_capture_passive`). Spoofing
`principal="engineering_os"` without the session token cannot obtain L2.
Builds run in a process group with SIGTERM→SIGKILL tree cleanup on timeout.

---

## Bring-up workflow statuses

| Status | Meaning |
|---|---|
| `blocked` | Missing hardware, ambiguous ID, or incomplete toolchain |
| `failed` | Build attempted and failed / timed out |
| `built` | Firmware compiled; **not** flashed or hardware-verified |
| `verified` | Not used for compile-only flows |

---

## Natural language

Discovery:

> Hey PYRA, check the devices connected to this PC.

Bring-up (L2 build when evidence allows):

> PYRA, connect to the NXP board and run a basic LED blink bring-up.

Reports land under `~/PyraWork/projects/<id>/reports/` (`discovery_*` / `bringup_*`).

---

## Safety

- No flash, erase, reset, OTP, or persistent configuration.
- Build success requires process exit evidence.
- Models cannot authorize L2/L3 or override VID/PID evidence.
