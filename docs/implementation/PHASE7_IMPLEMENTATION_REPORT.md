# Phase 7 — Implementation Report

**Date:** 2026-11-10  
**Baseline before Phase 7:** 233 tests passing  
**After Phase 7:** **252 passed**; `pip check` clean  
**Verdict:** `COMPLETE WITH DOCUMENTED RESTRICTIONS`

---

## Audit findings

| Area | Pre-Phase-7 state | Gap closed |
|---|---|---|
| Specialists | echo / broker_probe / research only | Seven engineering specialists registered |
| Orchestration | Single-capability handlers | Master `engineering_workflow` dependency-ordered fan-out |
| Project OS | Generic tasks/notes/artifacts | `artifacts/engineering/*` typed JSON store |
| L3 | `MAX_GRANTABLE=L2`; flash denied | L3 tools + Broker-minted single-use approvals |
| NeedsConfirm | Unused | Wired for programming approval / resume |
| Mark path | Bring-up stopped at L2 build | `ENGINEERING_WORKFLOW` intent → full specialist chain |

Frozen architecture (`docs/architecture/PYRA_ARCHITECTURE_BASELINE.md`) was not redesigned.

---

## Specialist agents implemented

| Agent ID | Responsibility | Output contract |
|---|---|---|
| `planning` | Project plan | `ProjectPlan` |
| `requirements` | Requirements / systems eng. | `SystemRequirements` |
| `architecture` | Project system architecture | `SystemArchitecture` |
| `hardware_eng` | Evidence-based hardware analysis | `HardwareDesign` |
| `firmware_eng` | Firmware design | `FirmwareDesign` |
| `verification` | Test plan + evidence evaluation | `VerificationPlan` / `VerificationReport` |
| `documentation` | Final engineering report | `EngineeringReport` |

All implement `SpecialistAgent` via `PydanticAISpecialistAgent`, registered through Agent Runtime bootstrap. Tests and Master orchestration use `force_deterministic=True` for reliable structured outputs; live model enrichment remains available via ModelGateway when not forced.

---

## Agent Runtime integration

- Bootstrap registers Phase 7 agents alongside research/echo/broker_probe.
- Master invokes specialists **only** via `AgentRuntime.run(AgentTask)`.
- No direct PydanticAI calls from Master.
- Agent max level remains L0/L1; specialists never receive L3 sessions.

---

## Master orchestration changes

- New intent: `IntentKind.ENGINEERING_WORKFLOW`.
- New module: `master/engineering_workflow.py`.
- Stage order: planning → requirements → architecture → hardware → firmware → Eng OS build → verification plan → **NeedsConfirm** → programming → verification report → documentation.
- Approval utterances (`approve programming confirm_…`) resume persisted workflow state.
- `CapabilityResult.needs_confirm` propagated by Orchestrator into `InteractResponse`.

---

## Project OS changes

- `project_os/engineering_artifacts.py` — save/load/list under `projects/<id>/artifacts/engineering/`.
- Workflow state, specialist outputs, and final report persisted as JSON (latest + stamped).
- No second project database.

---

## ModelGateway integration

- Specialists resolve models through shared `get_specialist_gateway()`.
- Deterministic synthesize path used for Phase 7 automated workflow reliability.
- No OpenRouter / LiteLLM migration.

---

## Engineering OS changes

- Existing discovery + L2 `bringup_build` reused inside the multi-specialist workflow.
- Programming/erase executed only via Broker L3 tools after approval (not embedded as “AI success”).

---

## Broker changes

- `MAX_GRANTABLE = L3`.
- `ENGINEERING_OS_L3_TOOLS = {program_firmware, erase_flash}`.
- `BrokerSession.l3_tools` + principal restriction (only `engineering_os`).
- `ApprovalStore` — operation-bound, project/board/device/hash/programmer/address, expiring, single-use.
- Approval consumed in `invoke` **before** backend; denials never call `_program_runner` / `_erase_runner`.
- Fail-closed when programmer backend unset.

---

## Hardware support

- Board profiles unchanged; identification remains evidence-based.
- Live host at demo: USB Arduino `2341:0043`; audio codec; **no** `/dev/ttyACM*`; **no** `west` / `avrdude` / `arm-none-eabi-gcc`; `openocd` present.
- NXP RT1170 EVKB **not** connected during live demo.
- Automated e2e uses injected RT1170 USB + mocked west/program backends.

---

## Build and programming

- Build: existing L2 `west_build` via Engineering OS.
- Programming: L3 `program_firmware` after Broker mint + human `NeedsConfirm`.
- Erase: separate `erase_flash` approval required.
- Live host: build blocked (no west); programming not prepared (no artifact) — reported as fail/partial honestly.

---

## Approval security

Covered by `tests/phase7/test_l3_approval.py`:

- Generic agent L3 grant denied
- Principal spoofing denied
- Forged session denied
- No-approval denied
- Replay denied
- Expiry denied
- Target substitution denied
- Artifact mutation fails closed
- Erase with program approval denied; separate erase approval required
- Backend invocation count verified on every denial

Phase 6.1 session isolation retained.

---

## Verification implementation

- Verification specialist never marks pass without evidence.
- Distinguishes build / program / startup evidence.
- Physical LED observation remains separate and unverified without instruments.

---

## Mark LIII integration

- Live smoke used Mark-shaped `InteractRequest(source="mark")` through Master Orchestrator (Dot contract preserved).
- Intent classified as `engineering_workflow`.
- All seven specialists executed; Project OS artifacts written.
- Raw output: `docs/implementation/phase7_live_demo_raw.json`.
- Standing Mark LIII voice process was not separately driven in this session; request path is the same Master entry Dot uses.

---

## Test results

| Suite | Result |
|---|---|
| Full regression | **252 passed** |
| `tests/phase7` | 19 passed |
| `pip check` | clean |

---

## Real hardware demonstration

| Step | Result |
|---|---|
| Mark-shaped request → Master | Demonstrated |
| Multi-specialist coordination | Demonstrated (7 agents) |
| Project OS persistence | Demonstrated |
| Live USB discovery | Arduino enumerated |
| Zephyr build | **Not demonstrated** (west missing) |
| Physical MCU program / runtime verify | **Not demonstrated** (no qualified RT1170 + programmer toolchain) |

---

## Known restrictions

1. Physical L3 program/verify of RT1170 EVKB not run on this host.
2. Arduino present but Phase 7 programming path targets qualified Zephyr board profiles; no avrdude ACM path.
3. Specialist workflow defaults to deterministic synthesize for reliability; live LLM enrichment is optional and not required for architecture proof.
4. Serial capture during resume requires an explicit device path (never invented).
5. Crash recovery limited to Project OS artifact persistence (no separate durable workflow engine / LangGraph).

---

## Final verdict

**`COMPLETE WITH DOCUMENTED RESTRICTIONS`**

Architecture coordination through Mark→Master→Project OS→Agent Runtime→specialists→Engineering OS→Device Broker was demonstrated with real specialist outputs and honest failure on missing toolchain/MCU. Full `COMPLETE AND ARCHITECTURE DEMONSTRATED` requires a supported connected MCU, host toolchain, and live programming + runtime verification.
