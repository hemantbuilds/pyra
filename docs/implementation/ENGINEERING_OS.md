# Engineering OS — Phase 4

**Status:** Complete (foundation + hardware discovery)  
**Package:** `agent-os/engineering_os/`  
**Master:** `master/engineering_service.py`, `master/engineering_handlers.py`

---

## Architecture

```text
Mark → Dot → Master → engineering_os
                         ↓
                   EngineeringOS.discover_hardware()
                         ├── Device Broker L0: USB / serial / probes / sysinfo
                         ├── identify.py (profiles + confidence caps)
                         ├── toolchain.py (readiness; no installs)
                         └── report → Project OS reports/ via Broker L1 write
```

Engineering OS never opens serial ports or runs host commands directly.

---

## Capabilities (Phase 4)

| Capability | Status |
|---|---|
| Hardware discovery | **Done** |
| Evidence-based identification | **Done** |
| Platform profiles | **Done** (small initial set) |
| Toolchain assessment | **Done** (read-only) |
| Discovery report artifact | **Done** |
| Flash / erase / UART I/O / GPIO | **Not in Phase 4** |

---

## Device Broker extensions

| Tool | Level |
|---|---|
| `enumerate_usb_devices` | L0 |
| `enumerate_serial_devices` | L0 |
| `enumerate_debug_probes` | L0 |

Allowlist additions: `lsusb`, `udevadm info …`, `pyocd --version`, `JLinkExe -?`, `STM32_Programmer_CLI --version`.

Write roots for active project now include `artifacts/` and `reports/` (L1).

Global L1 ceiling unchanged.

---

## Confidence model

| Level | Meaning |
|---|---|
| `confirmed` | Strong evidence (e.g. known probe VID/PID). MCU silicon still not claimed from USB alone for boards. |
| `probable` | Full VID/PID profile match for a board family |
| `possible` | Partial string / VID-only hints |
| `unknown` | Insufficient evidence |

Development boards: USB match is capped at **probable** for board family; MCU remains unresolved without more evidence.

---

## Platform profiles

Data in `engineering_os/platforms/profiles.py` (not hardcoded defaults in discovery logic):

Arduino-compatible, ESP USB-UART, STM32 ST-LINK, NXP/CMSIS-DAP, Pico, CMSIS-DAP probe, J-Link, FTDI adapter.

---

## Run

```bash
cd /home/hem/pyra/agent-os && .venv/bin/python -m master
```

Say via Mark (with Master up):

> Hey PYRA, check the devices connected to this PC.

Or curl:

```bash
curl -s -X POST http://127.0.0.1:8765/dot/v1/interact \
  -H 'Content-Type: application/json' \
  -d '{"text":"check the devices connected to this PC","source":"mark","metadata":{"from_mark":true}}'
```

Reports land in `~/PyraWork/projects/<id>/reports/discovery_*.txt`.
