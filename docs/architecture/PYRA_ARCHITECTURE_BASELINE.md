# PYRA Architecture Baseline

| Field | Value |
|---|---|
| **Architecture name** | PYRA Personal AI Operating System |
| **Architecture version** | **1.0** |
| **Baseline status** | **FROZEN WITH DOCUMENTED OPEN VALIDATION ITEMS** |
| **Freeze date** | 2026-11-10 |
| **Primary host** | Raspberry Pi 5 (ARM64), extensible |
| **Authority** | This document is the primary architectural reference for implementation |

**Related packages:**  
- Historical design: `docs/architecture/00`–`14` (2026-11-09 planning)  
- Technology adoption: `docs/architecture/technology-adoption/`  
- Implementation status: `docs/implementation/`  
- Freeze review: [`ARCHITECTURE_FREEZE_REVIEW.md`](ARCHITECTURE_FREEZE_REVIEW.md)

Implementation may proceed against this baseline. Architectural deviations require an Architecture Change Request (see §11.7).

---

## 11.1 Baseline identity & scope

PYRA is a personal AI operating system coordinated by a custom Master, with Mark-LIII as the user face, Dot as the Mark↔PYRA router, Project OS as authoritative project state, Device Broker as the mandatory tool/hardware security boundary, Engineering OS as engineering workflow owner, and Agent Runtime as specialist lifecycle owner.

**Completed implementation (code):** Phases 0–4; **Phase 5b** Agent Runtime; **Phase 5c** PydanticAI Research Agent; **Phase 5d** ModelGateway evaluation (invoke/retry/cancel, Ollama benchmarks; LiteLLM deferred).

**Not yet implemented:** Additional specialists; cloud/OpenRouter; L2/L3 execution; operation-bound approval tokens; official MCP SDK migration (5a); LangGraph workflows.

---

## 11.2 Frozen architectural principles

1. Mark-LIII is retained as the existing user interface.  
2. Dot is the required integration boundary between Mark and PYRA.  
3. Master is the central coordinator (intent, delegation, approvals, responses).  
4. Project OS is the authoritative persistent project-state system.  
5. Agent Runtime owns specialist agent execution lifecycle.  
6. PydanticAI implements individual specialists (behind Runtime).  
7. LangGraph is **optional and selective** for durable multi-step engineering workflows only.  
8. ModelGateway is a PYRA-owned provider abstraction.  
9. Device Broker is the **mandatory** tool and hardware security boundary.  
10. **Internal** agent tool calls use **BrokerClient → Device Broker** (not MCP as a mandatory hop).  
11. **MCP** is for **external interoperability** (and optional external MCP servers), not mandatory internal agent communication.  
12. Engineering OS owns engineering workflows and evidence rules.  
13. n8n remains a separate Automation OS plane (not the brain).  
14. Human approval for sensitive ops is **bound to exact operation details**.  
15. Hardware operations must never bypass Device Broker.  
16. Project context and persistent state remain isolated per project.  
17. Hardware identity must be evidence-based (no hardcoded default board).  
18. **Build success ≠ flash success ≠ runtime verification** — report separately.

---

## 11.3 High-level architecture (frozen)

```text
User
  ↓
Mark-LIII
  ↓
Dot
  ↓
PYRA Master ──► ModelGateway ──► Ollama / cloud provider(s)
  ↓
Project OS (authoritative state)
  ↓
Agent Runtime
  ↓
PydanticAI specialists
  ↓
BrokerClient          ←── internal tool path (mandatory)
  ↓
Device Broker (policy · validate · execute · audit)
  ↓
Approved tools / host / hardware

Optional / separate:
  Engineering OS (+ selective LangGraph) → BrokerClient → Device Broker
  External MCP client → MCP adapter → Device Broker (same policy)
  n8n (Automation OS)
  Playwright via Broker browser tools (when adopted)
```

---

## 11.4 Component ownership (frozen)

| Component | Owns | Must not own |
|---|---|---|
| Mark-LIII | Face / voice / HUD | Orchestration, Project OS, Broker |
| Dot | Mark↔Master routing | Project state, agents, hardware |
| Master | Coordination, delegation, approvals UX binding | Specialist internals, hardware auth |
| Project OS | Persistent project truth | Agent execution, tool policy |
| Agent Runtime | Specialist lifecycle & contracts | Independent project DB |
| PydanticAI | Specialist implementations | Hardware authorization |
| LangGraph | Selected durable workflows | Master role, Project OS truth |
| ModelGateway | Provider abstraction | Project state, tools |
| BrokerClient | Internal broker access API | Permission authority |
| Device Broker | Authorization, validation, execution, audit | Project workflow decisions |
| Engineering OS | Eng workflows & evidence | Uncontrolled hardware access |
| MCP adapter | External interoperability | Independent security policy |
| n8n | Deterministic personal automation | PYRA brain / agent coordinator |

---

## 11.5 Frozen technology decisions

| Technology | Decision |
|---|---|
| Mark-LIII, Dot, Master, Project OS, Device Broker, Engineering OS | **RETAIN** (custom cores) |
| Agent Runtime | **RETAIN/BUILD** custom abstraction |
| BrokerClient | **RETAIN/BUILD** internal tool interface |
| PydanticAI | **ADOPT** — specialists |
| LangGraph | **CONDITIONAL / SELECTIVE** — durable Eng workflows only |
| Official MCP Python SDK | **EVALUATE** (PoC); adopt for **external** MCP if PoC passes; keep custom MCP until then |
| Custom MCP JSON-RPC | **RETAIN** until PoC passes |
| ModelGateway | **RETAIN** PYRA-owned |
| LiteLLM SDK | **CONDITIONAL** — adopt only if PoC shows measurable value |
| LiteLLM Proxy | **DEFER** (not on Pi) |
| Ollama | **RETAIN** |
| PlatformIO / Zephyr west / pyOCD / OpenOCD / probe-rs / esptool | **ADOPT AS REQUIRED** via Broker |
| Playwright | **ADOPT WHEN REQUIRED** via Broker |
| n8n | **RETAIN** separately |
| OpenTelemetry | **ADOPT INCREMENTALLY** |
| Langfuse / Phoenix | **DEFER** |
| Renode / Labgrid / Docling / Qdrant / Chroma / A2A / ACP | **DEFER** |
| CrewAI | **REJECT** |
| OpenClaw as foundation | **REJECT** |
| cFS | **EXCLUDED** |

Detail matrix: [`technology-adoption/03_TECHNOLOGY_ADOPTION_MATRIX.md`](technology-adoption/03_TECHNOLOGY_ADOPTION_MATRIX.md)

---

## 11.6 Frozen security invariants

1. No unrestricted shell access for agents.  
2. No direct agent-to-hardware access.  
3. No Broker policy bypass (including via MCP, LangGraph, or ModelGateway).  
4. No agent self-authorization of sensitive operations.  
5. No agent permission self-escalation.  
6. No reusable generic approval for L3 / sensitive ops — **operation-bound, one-time tokens**.  
7. No unauthenticated external MCP exposure (localhost / auth required).  
8. No secrets in ordinary logs or Project memory.  
9. No cross-project context leakage.  
10. No automatic flash/erase without explicit operation-bound human approval.  
11. Device Broker independently validates approval; agent claims are insufficient.  
12. Serial enumeration ≠ passive capture ≠ command TX ≠ persistent config ≠ flash.

### Permission levels (normative)

| Level | Scope |
|---|---|
| L0 | Read-only discovery / inspection |
| L1 | Controlled workspace / approved non-destructive ops |
| L2 | Builds, controlled execution, approved serial command TX (as classified) |
| L3 | Flash, erase, sensitive persistent hardware configuration |

### Serial classification (normative)

| Operation | Class |
|---|---|
| Enumerate serial / read metadata / identify interfaces | L0 |
| Open serial connection | Controlled (scoped) |
| Passive serial capture | L0/L1 (bounded) |
| Send UART / device commands | L2+ (impact-dependent) |
| Persistent device settings | L3 where applicable |
| Flash / erase | L3 + operation-bound approval |

### Approval lifecycle (sensitive ops)

`REQUESTED → VALIDATED → WAITING_FOR_APPROVAL → APPROVED → EXECUTING → COMPLETED|FAILED|DENIED|EXPIRED`

Tokens: server-generated, one-time, expiring, bound to project/task/device/artifact hash/operation params; validated only by Device Broker.

---

## 11.7 Frozen implementation roadmap

| Phase | Status | Objective |
|---|---|---|
| 0–4 | **Completed** | Audit, Master/Dot, Project OS, Device Broker, Eng OS discovery |
| 5a | Planned | MCP SDK PoC (external interoperability path) — **does not block 5b** |
| 5b | **Completed** | Agent Runtime foundation + BrokerClient (deterministic agents only) |
| 5c | **Completed** | PydanticAI adapter + Research Agent (`research`) |
| 5d | **Completed (with limitations)** | ModelGateway eval; LiteLLM **deferred**; small-model live limits documented |
| 6 | Planned | Eng OS L2: build + controlled serial |
| 7 | Planned | Eng OS L3: operation-bound flash + runtime verify |
| 8 | Planned | Selective LangGraph for durable eng workflows |
| 9 | Planned | Playwright + expanded n8n |
| 10 | Planned | OTEL + deferred tracer/docs intelligence |
| 11 | Planned | Evaluate A2A / ACP |

**Sequencing rules:** Internal agents use BrokerClient regardless of MCP SDK outcome. ModelGateway abstraction before mandatory provider library. No LangGraph before a real durable workflow. No L3 flash before operation-bound approval is designed/validated in implementation. Do not adopt deferred tech “to fill the roadmap.”

---

## 11.8 Architecture change-control policy

**Architecture freeze** locks: system boundaries, ownership, security invariants, technology *direction*, and integration contracts.

**Implementation flexibility** allows: internal classes, file layout, algorithms, and local refactors that do not change those contracts.

After freeze:

1. Implementation work must follow this baseline.  
2. Agents/developers must read this document before architectural choices.  
3. No silent replacement of selected technologies.  
4. No new framework/service without an Architecture Change Request (ACR).  
5. ACR must state problem, alternatives, impact, risks, migration, compatibility.  
6. Security-boundary changes require explicit human review.  
7. Approved changes bump baseline version and update ADRs.  
8. Routine bugfixes that preserve contracts do not need an ACR.

---

## 11.9 Open validation items (do not claim passed)

| ID | Item | Status |
|---|---|---|
| OV-1 | Official MCP SDK + Broker security PoC | Not run |
| OV-2 | PydanticAI specialist + BrokerClient PoC | Not run |
| OV-3 | LiteLLM SDK vs direct provider measurable value | Not run |
| OV-4 | LangGraph durable bring-up skeleton | Not run |
| OV-5 | Operation-bound approval token implementation | Not implemented |
| OV-6 | Pi RAM measurements for always-on set | Not measured in this freeze |

**Baseline status reason:** Architecture decisions are frozen; several technology adoptions remain conditional on PoCs.
