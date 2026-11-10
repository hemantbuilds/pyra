# Test Results

## Combined Phase 1–4 automated tests

**Executed:** 2026-11-10  
**Command:**

```bash
/home/hem/pyra/agent-os/.venv/bin/python -m pytest \
  /home/hem/pyra/tests/engineering_os \
  /home/hem/pyra/tests/device_broker \
  /home/hem/pyra/tests/master \
  /home/hem/pyra/tests/project_os -q
```

**Result: 63 passed, 0 failed** (1.46s)

| Suite | Role |
|---|---|
| `tests/engineering_os` | Discovery, ID confidence, toolchain, project isolation, Master/Dot |
| `tests/device_broker` | Phase 3 regression + security |
| `tests/master` | Phase 1 regression (bring-up now → engineering_os) |
| `tests/project_os` | Phase 2 regression |

## Live hardware discovery (this host)

**Executed:** 2026-11-10 — real USB/serial enumeration (not mocked).

Observed:

| Node | Evidence | Identification |
|---|---|---|
| `/dev/ttyACM0` | VID `2341` PID `0043`, manufacturer Arduino, product Uno R3 (CDC ACM) | Arduino Uno-compatible — **probable** (MCU not confirmed beyond USB) |
| `/dev/ttyAMA0` | No USB metadata (SoC UART) | **unknown** |
| `/dev/ttyAMA10` | No USB metadata | **unknown** |

Also: `usb_count: 2`, readiness `partially_ready`, `flash_attempted: false`, report written under project `reports/`.

Host tools present included `lsusb`, `udevadm`, `openocd`.

**Note:** Live result documents this Pi’s attached devices at test time; CI/mocked tests remain the regression gate.
