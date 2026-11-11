# Phase 6 — Gap Analysis (pre-implementation)

**Date:** 2026-11-10  
**Branch:** `main`  
**Baseline tests:** 170 passed / 0 failed / 0 skipped  
**pip check:** clean  
**Constraint:** Preserve all existing uncommitted Phase 5b–5d.1 work. No commit/push. Extend Phase 4 discovery — do not rewrite it.

---

## 1. Existing Engineering OS capabilities

| Area | Status | Location |
|---|---|---|
| Hardware discovery orchestration | Done | `engineering_os/discovery.py` |
| USB / serial / probe via Broker L0 | Done | Broker `enumerate_*` tools |
| Profile matching + confidence caps | Done | `identify.py`, `platforms/profiles.py` |
| Toolchain readiness (read-only) | Done | `toolchain.py` |
| Discovery reports | Done | `report.py`, `service.py` |
| Master `HARDWARE_DISCOVERY` / `HARDWARE_BRINGUP` | Discovery only | `master/engineering_handlers.py` |
| L2 build / blinky prep / serial capture / bring-up workflow | **Missing** | — |

Bring-up intent currently appends “not enabled yet” and still runs discovery only.

---

## 2. Existing Device Broker capabilities

| Area | Status |
|---|---|
| Permission L0–L3 enum | Present |
| Grantable ceiling | **`PHASE3_MAX_GRANTABLE = L1`** — blocks all L2/L3 |
| USB / serial enumerate (no open) | L0 done |
| Debug probe tool presence | L0 done |
| Allowlisted commands | L1 `run_allowed_command` (version probes only) |
| Workspace FS read/write | L0/L1 done |
| Audit SQLite | Done |
| Path jail / project isolation | Done |
| Flash / erase / L3 tools | **Not registered** (unknown → denied) |
| `west build` / serial capture | **Missing** |

---

## 3. Device enumeration

- USB: sysfs + optional `lsusb` via Broker.
- Serial: `/dev/ttyACM*`, `ttyUSB*`, `ttyAMA*` + by-id + udev metadata; **ports never opened**.
- Probes: executable presence (`openocd`, `pyocd`, `JLinkExe`, …) — not USB probe identity sessions.

**Gap:** Richer board-specific profile for i.MX RT1170 EVKB / MCU-Link; structured identification result fields (`identified`, `board_id`, `candidate_boards`) for workflow consumption. Extend profiles/identify — do not replace USB enumerator.

---

## 4. Toolchain / SDK discovery

- `get_available_toolchains` / `get_installed_tool_versions` (PATH/`which`).
- `assess_toolchain` aggregates readiness; SDK paths largely `unknown`.

**Gap:** Explicit Zephyr/`west`/CMake/Ninja/arm-none-eabi compatibility report for build gating; PlatformIO detection; version capture for build evidence. Extend `toolchain.py`; optional Broker version probes already partially exist.

---

## 5. Command execution

- Prefix allowlist, no shell, metachar filter, cwd jail, timeout/output bounds.
- Env inherited; no controlled env allowlist yet.
- Timeouts (~15s) too short for real builds.

**Gap:** Dedicated L2 `west_build` (structured argv, workspace cwd, longer timeout, controlled env). Do **not** add generic shell or raise L1 allowlist to arbitrary commands.

---

## 6. Permission levels

| Level | Meaning | Phase 6 |
|---|---|---|
| L0 | Discovery | Keep |
| L1 | Workspace / allowlisted cmds | Keep; ResearchAgent stays ≤ L1 |
| L2 | Controlled build + passive serial | **Enable narrowly** |
| L3 | Flash/erase/persist | **Remain denied** |

Engineering OS may call L2 tools. AgentBrokerSession defaults / ResearchAgent must **not** inherit L2 globally.

---

## 7. Project workspace

Project OS owns identity; Broker write roots include project `workspace`, `artifacts/`, `reports/`.  
**Gap:** Deterministic firmware prep under project workspace (e.g. `firmware/zephyr_blinky/`); never LLM-supplied absolute paths without jail.

---

## 8. Serial

Enumerate L0 done. Open / capture / TX **missing**.  
**Phase 6 plan:** L2 bounded passive capture only. UART TX left **unavailable** unless a narrow safe path is proven — default: document as unavailable (prefer fail-closed).

---

## 9. Missing capabilities (implementation list)

1. Raise grantable ceiling to L2 (rename constant; keep L3 blocked).
2. Board profile `imxrt1170_evkb` + `zephyr_board` metadata; structured ID API for workflow.
3. Build-environment discovery (Zephyr/PlatformIO readiness).
4. Broker L2 tools: `west_build`, `serial_capture_passive` (+ injectable backends for tests).
5. Explicit L3 denial regression (flash/erase/persist names).
6. Zephyr blinky preparation (deterministic file set via L1 writes).
7. Engineering OS bring-up workflow + operation states (`planned|running|blocked|failed|built`).
8. Master bring-up routing → workflow (not discovery-only).
9. Comprehensive unit / integration / e2e / security tests.

---

## 10. Files to modify

| File | Change |
|---|---|
| `device_broker/permissions.py` | L2 ceiling |
| `device_broker/broker.py` | Longer build exec path / env; ceiling messages |
| `device_broker/policy.py` | Build timeout/output knobs |
| `device_broker/tools/registry.py` | Register new tools |
| `engineering_os/platforms/profiles.py` | RT1170 profile + zephyr_board |
| `engineering_os/identify.py` | Structured board ID result helpers |
| `engineering_os/toolchain.py` | Zephyr/PIO readiness |
| `engineering_os/service.py` | Workflow entrypoints |
| `master/engineering_handlers.py` | Bring-up → L2 workflow |
| `master/capabilities.py` | Risk/docs if needed |

## 11. New modules (genuinely required)

| Module | Purpose |
|---|---|
| `device_broker/tools/build_tools.py` | L2 west build |
| `device_broker/tools/serial_tools.py` | L2 passive capture |
| `engineering_os/build_env.py` | Build-system compatibility |
| `engineering_os/firmware_prep.py` | Zephyr blinky scaffold |
| `engineering_os/workflow.py` | Deterministic bring-up orchestration |
| `engineering_os/states.py` | Operation status constants |
| `tests/engineering_os/test_phase6_*.py` | Unit/integration/e2e/security |

---

## 12. Proposed sequence

1. Permissions + L2 tools (mockable) + L3 denial tests  
2. Board profile + ID structuring + discovery tests  
3. Build env discovery  
4. Firmware prep + west_build evidence  
5. Serial passive capture  
6. Workflow + Master  
7. Full regression  

---

## 13. Security implications

- L2 must be tool-scoped, not a blanket shell.
- ResearchAgent / unrelated agents remain max L1.
- No model-based authorization; no Broker bypass.
- No flash/erase/reset/persist APIs.
- Path jail + argv validation + audit for every L2 invoke.
- Build success = process exit status + evidence only.

---

## 14. Non-goals

No OpenRouter/LiteLLM, no live AI tool-calling dependency, no Phase 7 approval mechanism, no architecture baseline redesign, no commit/push.
