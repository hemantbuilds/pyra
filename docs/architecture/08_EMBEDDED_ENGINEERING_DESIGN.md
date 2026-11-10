# Document 8 — Embedded Engineering Design

---

## 1. Goal

Move from spoken/typed objective to a **tested, documented** embedded system with persistent evidence — without claiming hardware success from software-only signals.

---

## 2. End-to-end lifecycle

| Phase | Agent lead | Key outputs | Exit criteria |
|---|---|---|---|
| Intake | master + project_mgr | PROJECT.md, requirements draft, open questions | Critical constraints answered or explicitly TBD |
| Systems | systems | SysReq, architecture, ICD, risk register, V&V matrix | Interfaces named; risks ranked |
| Hardware plan | hardware | Block diagram, BOM draft, bring-up matrix | Human EE review flagged |
| Repo scaffold | firmware/software | workspace git, CI skeleton, README | Builds empty/hello world |
| Bring-up | lab + firmware | Power/clock/reset/JTAG/UART checklist with logs | Evidence objects per step |
| Firmware impl | firmware (+ACP) | Drivers, apps, unit tests | Build green + on-target smoke where HW present |
| Host tools | software | Flash scripts, dashboards, packs | Reproducible commands in docs |
| Validation | testing | Test reports, HIL results | Trace to requirements |
| Closeout | docs + project_mgr | Release notes, artifact pack | Project state completed/archived |

---

## 3. Intake template (generated, then filled)

Mandatory fields: objective, MCU/SoC family (if known), interfaces, power budget, realtime constraints, safety class, environment, NRE/schedule, lab equipment available, repo preferences.

Master asks only for **missing critical** fields (not a 40-question interrogation).

---

## 4. Bring-up as first-class workflow

Checklist items become tasks with required `evidence`:

```json
{
  "step": "uart_boot_log",
  "status": "done",
  "evidence": {
    "type": "serial_capture",
    "path": "artifacts/bringup/uart0.log",
    "matched": ["boot", "Hello"]
  }
}
```

Rules:
- Build success ≠ power OK ≠ JTAG OK ≠ application OK.  
- If no board attached, steps stay `blocked` with reason `no_target`.  
- Lab agent owns serial port lock.

Integrations (Phase 7): OpenOCD, pyOCD, probe-rs, esptool, pyserial, optional instrument APIs later (scope, LA, PSU).

---

## 5. Firmware / software loop

```
edit (ACP/cloud) → build tool → parse diagnostics → fix
                 ↘ flash (L3 approve) → serial observe → evidence
```

Toolchain matrix (project-selectable templates):
- Zephyr + west  
- ESP-IDF  
- STM32Cube / CMake  
- NXP MCUXpresso / CMake  
- Generic GCC+CMake  

---

## 6. Hardware / KiCad

- Assistive only: symbol/footprint research, ERC/DRC invocation via KiCad CLI when installed.  
- **No autonomous “schematic is correct” claim.**  
- BOM includes manufacturer P/N + datasheet links as untrusted-fetched docs stored under `artifacts/datasheets/`.

---

## 7. Testing hierarchy

Static → unit (host/qemu) → integration → on-target smoke → HIL → regression pack.  
MISRA/clang-tidy optional per project profile.  
Reports land in `artifacts/test/`.

---

## 8. Engineering knowledge base

Per project:
- Datasheets (files + metadata)  
- Decision records (`decision.*` events)  
- Known issues list  
- Bring-up history  
- Pinmux / clock notes  

Retrieval: structured first; embeddings optional later.

---

## 9. Explicit non-goals (v1)

- Full autonomous PCB layout sign-off  
- Certification artifacts (DO-178, ISO 26262) as automated legal sign-off  
- NASA cFS (forbidden by assignment)  
