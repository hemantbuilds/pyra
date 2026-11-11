# Phase 7 — Architecture Conformance Report

**Reference:** `docs/architecture/PYRA_ARCHITECTURE_BASELINE.md`  
**Date:** 2026-11-10  
**Related:** `PHASE7_IMPLEMENTATION_REPORT.md`, `PHASE7_PLAN.md`

Classification key:

- `IMPLEMENTED_AND_DEMONSTRATED` — exercised in live or Mark-shaped end-to-end run with evidence
- `IMPLEMENTED_NOT_DEMONSTRATED` — code present; not exercised live in this phase
- `PARTIALLY_IMPLEMENTED` — core path exists with documented gaps
- `DEFERRED_BY_ARCHITECTURE` — intentionally later / out of Phase 7 scope
- `NOT_IMPLEMENTED` — expected by baseline but missing without deferral rationale

---

## Core control plane

| Component | Expected | Actual | Invocation path | Evidence | Tests | Classification |
|---|---|---|---|---|---|---|
| Mark LIII | Voice UX | Existing; not rebuilt | User → Mark → Dot | Mark-shaped InteractRequest smoke | Router tests | `PARTIALLY_IMPLEMENTED` (path proven; live voice session not driven this run) |
| Dot | Mark↔Master bridge | Existing DotGateway | `/dot/v1/interact` | Contract preserved | Dot/Master tests | `IMPLEMENTED_NOT_DEMONSTRATED` (API path unchanged; this demo used Master Orchestrator directly with `source=mark`) |
| PYRA Master | Central coordinator | Orchestrator + engineering_workflow | classify → capability → workflow | Live demo intent + specialist fan-out | phase7 workflow tests | `IMPLEMENTED_AND_DEMONSTRATED` |
| Project OS | Authoritative project state | ProjectOS + engineering_artifacts | Master/Eng OS writes | Artifact tree in live demo | Project OS + phase7 | `IMPLEMENTED_AND_DEMONSTRATED` |
| Agent Runtime | Specialist lifecycle | AgentRuntime + bootstrap | Master → runtime.run | 7 agents in live demo | agent_runtime + phase7 | `IMPLEMENTED_AND_DEMONSTRATED` |
| PydanticAI | Specialist implementation | PydanticAISpecialistAgent subclasses | Runtime → agent.run | Registered specialists | specialists tests | `IMPLEMENTED_AND_DEMONSTRATED` (deterministic synthesize exercised; LLM path available) |
| ModelGateway | Sole model abstraction | Existing ModelGateway | Specialist gateway resolve | Shared gateway wiring | model_gateway tests | `IMPLEMENTED_AND_DEMONSTRATED` (wiring); live LLM specialist run optional |
| Engineering OS | Deterministic eng workflows | discovery + bringup_build + L3 via Broker | Master workflow | Live discovery; mocked build e2e | engineering_os + phase7 | `PARTIALLY_IMPLEMENTED` |
| Device Broker | Execution + security boundary | L0–L3 + approvals | Eng OS client session | L3 security tests + live L0/L1 | phase61 + phase7 L3 | `IMPLEMENTED_AND_DEMONSTRATED` |
| Linux host tools | Discovery/build/program | Broker tools | west_build, serial, program_firmware | Discovery live; west absent on host | phase6/7 | `PARTIALLY_IMPLEMENTED` |
| MCU | Program + runtime verify | Qualified boards only | L3 program_firmware | Automated mock program; no live MCU program | phase7 L3 + workflow | `IMPLEMENTED_NOT_DEMONSTRATED` |

---

## Specialist team

| Specialist | Classification | Notes |
|---|---|---|
| Planning | `IMPLEMENTED_AND_DEMONSTRATED` | Live + tests |
| Requirements | `IMPLEMENTED_AND_DEMONSTRATED` | Distinguishes user vs derived |
| System Architecture | `IMPLEMENTED_AND_DEMONSTRATED` | Project-scoped (not PYRA redesign) |
| Hardware Engineering | `IMPLEMENTED_AND_DEMONSTRATED` | Evidence-based; unknowns recorded |
| Firmware Engineering | `IMPLEMENTED_AND_DEMONSTRATED` | Uses HW/requirements context |
| Verification | `IMPLEMENTED_AND_DEMONSTRATED` | No pass without evidence |
| Documentation | `IMPLEMENTED_AND_DEMONSTRATED` | Report from Project OS evidence |
| Research (prior) | `IMPLEMENTED_AND_DEMONSTRATED` | Retained; not coordinator |

---

## External / deferred architecture components

| Component | Baseline role | Phase 7 stance | Classification |
|---|---|---|---|
| MCP | External interoperability | Not used as Master↔Agent↔Broker bus | `DEFERRED_BY_ARCHITECTURE` |
| n8n | Deterministic automation plane | Not required for MCU workflow | `DEFERRED_BY_ARCHITECTURE` |
| ACP | Coding-agent interoperability | Not universal agent bus | `DEFERRED_BY_ARCHITECTURE` |
| LangGraph | Selected durable workflows | Agent Runtime remains primary | `DEFERRED_BY_ARCHITECTURE` |
| LiteLLM | Conditional provider layer | Not migrated | `DEFERRED_BY_ARCHITECTURE` |
| OpenRouter | Deferred provider | Not introduced | `DEFERRED_BY_ARCHITECTURE` |
| A2A | Deferred agent protocol | Not introduced | `DEFERRED_BY_ARCHITECTURE` |
| Playwright / desktop | Not required for MCU qual | Not introduced | `DEFERRED_BY_ARCHITECTURE` |
| OpenClaw / cFS | Out of scope | Not introduced | `DEFERRED_BY_ARCHITECTURE` |

---

## Security conformance

| Control | Status |
|---|---|
| Phase 6.1 session_id trust for L2+ | Intact |
| Agents cannot obtain Eng OS L3 session | Enforced |
| L3 requires Broker-minted approval | Enforced |
| Approval single-use / expiry / binding | Enforced |
| Separate erase approval | Enforced |
| No fabricated build/flash evidence | Enforced |

---

## Demonstration matrix (acceptance §13)

| Component | Live evidence this phase |
|---|---|
| Mark LIII | Mark-shaped request (`source=mark`) — voice stack not separately invoked |
| Dot | Contract unchanged; not re-exercised as HTTP hop in this smoke |
| Master | Workflow coordination + NeedsConfirm plumbing |
| Project OS | Plan/requirements/architecture/HW/FW/verification/report artifacts |
| Agent Runtime | Registration + 7 invocations |
| PydanticAI | Specialist classes behind interface |
| ModelGateway | Shared gateway for specialists |
| Specialists | All seven produced validated outputs |
| Engineering OS | Discovery + bring-up integration |
| Device Broker | Audit + L3 denial/allow tests; live discovery tools |
| Linux host | Real USB enumeration |
| MCU | **Not programmed live** |

---

## Verdict mapping

Phase 7 does **not** claim `COMPLETE AND ARCHITECTURE DEMONSTRATED` because physical MCU program + runtime verification on a qualified board was not completed on this host.

Architecture coordination of the frozen Hybrid Alt C control plane **was** demonstrated with multi-specialist structured handoffs and Broker security — hence **`COMPLETE WITH DOCUMENTED RESTRICTIONS`**.
