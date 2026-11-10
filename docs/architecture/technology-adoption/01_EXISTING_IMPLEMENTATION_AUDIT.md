# 01 — Existing Implementation Audit

**Inspection date:** 2026-11-10  
**Method:** Live tree, docs, `requirements.txt`, pytest collection, host probes  
**No code was modified for this audit.**

---

## 1. Host facts (verified)

| Item | Value |
|---|---|
| Machine | `aarch64` (Raspberry Pi class) |
| RAM | ~7.9 GiB total; ~3.3 GiB available at audit time |
| System Python | 3.13.5 |
| agent-os venv | Python 3.13.5 |
| Runtime deps declared | FastAPI, uvicorn, pydantic≥2.6, httpx, pytest |
| **Not** in deps | `mcp`, pydantic-ai, langgraph, litellm, playwright, labgrid |
| Tests collected | **63** |

---

## 2. Completed phases (actual)

| Phase | Status | Evidence |
|---|---|---|
| 0 Mapping | Complete | `docs/implementation/ARCHITECTURE_MAPPING.md` |
| 1 Master + Dot | Complete | `agent-os/master/`, `integrations/dot/`, `Mark-LIII/plugins/pyra_dot.py` |
| 2 Project OS | Complete | `agent-os/project_os/`, `~/PyraWork` layout |
| 3 Device Broker | Complete | `agent-os/device_broker/` (policy, tools, audit, minimal MCP) |
| 4 Eng OS discovery | Complete | `agent-os/engineering_os/` — discovery/identify/toolchain/report |

**Correction vs older planning text:** Engineering OS is **not** “missing.” Phase 4 discovery is implemented. Full bring-up/flash/HIL remain future.

---

## 3. Component inventory

### Mark-LIII
- Present as face; PYRA plugin `pyra_dot.py` posts to `/dot/v1/interact`.
- **Do not rebuild.**

### Dot
- In-process FastAPI route + `DotGateway` forwarder.
- Thin; correct boundary.

### Master
- FastAPI app, contracts (Pydantic), deterministic intent + Ollama fallback (`model_gateway.py`).
- Capability registry: system, project_os, device_broker, engineering_os, general.
- **No Agent Runtime yet** — specialists do not exist as a subsystem.

### Project OS
- SQLite authoritative; FS trees under `~/PyraWork/projects/<id>/`.
- Create/list/switch/tasks/memory/checkpoints/context_pack.
- **Must remain authoritative project memory.**

### Device Broker
- L0/L1 tools; Phase 3 ceiling L1; audit SQLite; path jail; command allowlist.
- Discovery tools: USB/serial/probes (sysfs + allowlisted cmds).
- MCP: **custom minimal stdio JSON-RPC** (`tools/list`, `tools/call`) — not official SDK.
- HTTP: `/broker/v1/tools`, `/broker/v1/call`.

### Engineering OS
- Orchestrates Broker for discovery; profile-based ID; toolchain assess; project reports.
- **Does not** flash, open UART for I/O, or build firmware yet.

---

## 4. Gaps (missing / partial)

| Area | State |
|---|---|
| Agent Runtime | Missing |
| Specialist agents | Missing |
| Official MCP SDK | Missing (custom subset only) |
| LiteLLM / multi-cloud gateway | Missing (Ollama HTTP only) |
| L2 build / L3 flash permissions | Defined in architecture; not granted/implemented |
| Serial I/O, flash, debug sessions | Missing |
| Playwright browser backend | Designed; not implemented |
| n8n Automation OS | Designed; not deployed in-repo |
| Observability (OTEL/Phoenix/Langfuse) | Missing |
| Docling / vector RAG | Missing |
| A2A | Missing |
| ACP coding sessions | Missing |

---

## 5. Replaceable custom pieces

| Custom piece | Recommendation |
|---|---|
| Minimal MCP stdio server | Candidate **REPLACE** with official `mcp` SDK **after PoC**, wrapping same Broker.invoke |
| Hand-rolled multi-provider routing (future growth) | Prefer LiteLLM SDK behind ModelGateway |
| Ad-hoc specialist “if intent then call LLM” | Prefer PydanticAI agents via Agent Runtime |

**Do not replace:** Project OS, Broker policy/audit/jail, Master capability bus, Dot, Mark plugin path.

---

## 6. Architectural conflicts to avoid

1. Letting LangGraph or n8n own project truth.  
2. Letting MCP clients call host tools without Broker.  
3. Running heavy always-on stacks (proxy + tracer + n8n + Ollama) concurrently on 8 GB without budgeting.  
4. Treating Phase 4 “Arduino probable” profile match as a hardcoded default board (it is evidence-based only).

---

## 7. Dependency tension (verified research)

Official MCP Python SDK v2 (`mcp` on PyPI) requires Python ≥3.11 (**OK**) and recent Pydantic/httpx2 stack. PYRA currently pins `pydantic>=2.6,<3` and `httpx>=0.27`. **Migration needs a dependency PoC** before REPLACE.

---

## 8. Summary judgment

Foundation is solid and coherent with Alternative C. The largest missing product layer is **Agent Runtime + specialists**, then **L2/L3 engineering execution** behind Broker. Protocol/tooling upgrades (MCP SDK, LiteLLM, Playwright) should be **adapters**, not rewrites.
