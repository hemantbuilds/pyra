# Engineering OS — Phase 4 Plan

**Status:** Implemented (see `ENGINEERING_OS.md`)  
**Date:** 2026-11-10  
**Scope:** Foundation + hardware-agnostic discovery only (no flash/serial I/O)

---

## Architecture

```text
Mark → Dot → Master → engineering_os capability
                         ↓
                   EngineeringOS.discover()
                         ├── Device Broker L0 tools (USB/serial/probes/sysinfo)
                         ├── Identification (profiles + evidence)
                         ├── Toolchain assessment
                         └── Project OS artifact (via Broker L1 write to reports/)
```

Engineering OS never opens `/dev` or runs host commands itself.

---

## Device Broker extensions (L0 unless noted)

| Tool | Level | Role |
|---|---|---|
| `enumerate_usb_devices` | L0 | sysfs USB enumeration (+ optional `lsusb`) |
| `enumerate_serial_devices` | L0 | ttyACM/USB + udev/sysfs metadata (no open) |
| `enumerate_debug_probes` | L0 | installed probe tooling presence/versions |
| `list_connected_devices_readonly` | L0 | kept (thin serial path list) |

Write-root extension (L1): active project `artifacts/` and `reports/` for discovery report storage.

New allowlisted cmds: `lsusb`, `udevadm info …` (path-validated), `pyocd`/`JLinkExe` version probes.

L1 ceiling unchanged. No serial write/open for I/O.

---

## Engineering OS package

```text
agent-os/engineering_os/
  service.py           # facade
  discovery.py         # orchestrates Broker evidence collection
  identify.py          # confidence model
  toolchain.py         # readiness assessment
  report.py            # structured + speech text
  platforms/profiles.py  # VID/PID / string profiles (data, not logic)
```

Confidence: `confirmed` | `probable` | `possible` | `unknown`

---

## Master

- Replace `hardware_bringup_stub` handler for discovery phrases with `engineering_os`.
- Intents: `hardware_discovery` (check devices / discover hardware) + keep `hardware_bringup` as discovery-for-now (still no flash; speech clarifies Phase 4 = discovery only).

---

## Out of scope

Flash, erase, reset, UART write, GPIO/SPI/I2C/CAN, firmware build, continuous monitoring.
