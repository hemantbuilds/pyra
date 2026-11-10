# PYRA Technical Planning Package — Index & Executive Summary

**Project:** Pyra Personal AI Operating System  
**Foundation:** Mark-LIII + pukkyAI + Raspberry Pi 5  
**Document type:** Architecture and implementation planning (no implementation in this package)  
**Date:** 2026-11-09  
**Status:** Discovery complete · Architecture selected · Ready for design review before coding  

---

## How to read this package

| Doc | File | Purpose |
|---|---|---|
| 0 | This file | Executive summary, recommendations, reading order |
| 1 | [`01_EXISTING_SYSTEM_AUDIT.md`](01_EXISTING_SYSTEM_AUDIT.md) | Mark-LIII, pukkyAI, host facts |
| 2 | [`02_TECHNOLOGY_RESEARCH.md`](02_TECHNOLOGY_RESEARCH.md) | Frameworks, protocols, models, tools |
| 3 | [`03_OVERALL_SYSTEM_ARCHITECTURE.md`](03_OVERALL_SYSTEM_ARCHITECTURE.md) | Alternatives A/B/C, selected hybrid |
| 4 | [`04_MASTER_AI_DESIGN.md`](04_MASTER_AI_DESIGN.md) | Local master, router, orchestration |
| 5 | [`05_AGENT_TEAM_DESIGN.md`](05_AGENT_TEAM_DESIGN.md) | Specialist agents, contracts, collab |
| 6 | [`06_PROJECT_OS_DESIGN.md`](06_PROJECT_OS_DESIGN.md) | Multi-project persistence |
| 7 | [`07_DEVICE_OS_DESIGN.md`](07_DEVICE_OS_DESIGN.md) | Linux/browser/desktop control |
| 8 | [`08_EMBEDDED_ENGINEERING_DESIGN.md`](08_EMBEDDED_ENGINEERING_DESIGN.md) | E2E embedded lifecycle |
| 9 | [`09_AUTOMATION_DESIGN.md`](09_AUTOMATION_DESIGN.md) | n8n + personal workflows |
| 10 | [`10_SECURITY_ARCHITECTURE.md`](10_SECURITY_ARCHITECTURE.md) | Threat model, levels, broker |
| 11 | [`11_DEPLOYMENT_ARCHITECTURE.md`](11_DEPLOYMENT_ARCHITECTURE.md) | Pi services, budgets, monitoring |
| 12 | [`12_IMPLEMENTATION_ROADMAP.md`](12_IMPLEMENTATION_ROADMAP.md) | Phases 0–9, critical path |
| 13 | [`13_RISK_REGISTER.md`](13_RISK_REGISTER.md) | Risks and mitigations |
| 14 | [`14_ARCHITECTURE_DECISION_RECORDS.md`](14_ARCHITECTURE_DECISION_RECORDS.md) | ADRs + prior-plan review |

**Interactive overview canvas:**  
[`pyra-architecture-selection.canvas.tsx`](/home/hem/.cursor/projects/home-hem-pyra/canvases/pyra-architecture-selection.canvas.tsx)

**Supersedes (as proposal):** [`../PYRA_AGENT_TEAM_PLAN.md`](../PYRA_AGENT_TEAM_PLAN.md) — retained as historical input; decisions reclassified in Doc 14.

---

## Executive summary

### What PYRA is

PYRA is a **personal AI operating system** behind Mark-LIII. Mark remains the wake/voice/HUD interface. A separately running **Master service** coordinates projects, specialist agents, device tools, and n8n workflows. The platform specializes in **end-to-end embedded engineering** while also supporting general personal automation.

### What exists today (verified)

| Asset | Reality |
|---|---|
| Mark-LIII folder | Upstream Mark LVI-class voice assistant (~2.8k-line `main.py`, ~7.5k-line `ui.py`); rich tools; **not** a multi-agent OS |
| pukkyAI | 336-line Ollama tool loop; working prototype for local master patterns |
| Host | Pi 5, 4× Cortex-A76, 7.9 GiB RAM, Debian 13, **labwc/Wayland**, Hailo-8 OK, Ollama 0.14 with `qwen2.5:3b` + `gemma3:1b`, Docker 26 without Compose plugin, **no Node.js**, no serial devices attached, Mark `.venv` pip broken |
| Prior plan | Directionally correct; several recommendations need modification (see Doc 14) |

### Recommended architecture (Alternative C — Hybrid)

**Do not** rebuild Mark. **Do not** adopt OpenClaw as the foundation. **Do** build a thin custom core and reuse industry protocols and selected subsystems:

```
Mark-LIII (face) ──HTTP──► Pyra Master API (local)
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
         Project OS     Agent Runtime    Device Broker
         (SQLite+FS)    (specialists)    (MCP + levels)
                              │               │
                              ▼               ▼
                         Cloud/ACP        n8n (MCP)
                         coding agents    workflows
```

| Subsystem | Selected tech | Rejected / deferred |
|---|---|---|
| Face | Mark-LIII plugin only | Forking `main.py` |
| Master | Custom Python FastAPI + Pydantic contracts; pukky lineage | OpenClaw gateway as core; CrewAI |
| Orchestration durability | Custom task graph + SQLite checkpoints; **evaluate LangGraph** in Phase 4 for engineering pipelines | AutoGen (maintenance); Temporal (too heavy for Pi) |
| Tools | MCP (stdio + Streamable HTTP) | New proprietary RPC |
| Coding agents | ACP adapters (Phase 8); scoped cloud agents earlier | ACP as universal agent bus |
| Personal automation | n8n via MCP/webhooks | LLM reinventing every integration |
| Desktop | Capability matrix + backends: Playwright first; X11 optional; Wayland limited | Assuming pyautogui works on Wayland |
| Local LLM | Ollama; Master on small Qwen; structured JSON + schema validation | Hailo for chat LLM |
| Secrets | OS keyring / env / sealed store; not next to Mark plaintext long-term | Prompt-as-security |

### Critical path (first shippable vertical)

1. Host feasibility notes + X11/Wayland decision (Phase 0)  
2. Master API + local Ollama router (Phase 1)  
3. Project OS create/switch/resume (Phase 2)  
4. Device broker MCP: fs + shell (Level 0–1) (Phase 3)  
5. Mark plugin → Master (Phase 5 can start in parallel after 1)  
6. One cloud specialist + one n8n workflow (Phases 4 & 6)  
7. Serial/flash evidence loop (Phase 7)

### Non-negotiable design rules (from assignment)

Mark stays loosely coupled. Cloud is optional for basic operation. Project state is never “only in chat.” Agents are least-privilege. n8n is not the brain. MCP is not the orchestrator. ACP is coding-session protocol. Hailo is perception, not assumed LLM. Wayland is not X11. No NASA cFS. No coding until this package is reviewed.

### Definition of done (platform)

See Doc 12. Short form: wake Pyra → create/switch projects without amnesia → Master local → specialists scoped → device actions verified → at least one embedded evidence path (build≠hardware-ok) → at least one n8n life workflow → Level 3 actions human-gated.

---

## Explicit unknowns / deferred measurements

| Item | Status |
|---|---|
| Local model tokens/s and tool-call reliability on *this* Pi | **Not benchmarked** this assignment (no install/change). Models present; community RPi5 numbers cited in Doc 2. Phase 0 must measure. |
| Playwright browsers installed in Mark venv | Unverified; venv `pip` broken (`required file not found`) |
| docker-compose-plugin | Missing; n8n deploy needs plugin or `docker-compose` binary |
| Node.js | Missing; required if any TS MCP servers or n8n community nodes need it — prefer Python MCP first |
| Serial/JTAG hardware | None attached now |
| OpenClaw ARM64 memory footprint on 8 GB with Mark+Ollama | Not measured; treated as risk if Alternative B revisited |

---

## Review checkpoint before implementation

Before Phase 1 coding, the owner should confirm:

1. Architecture **C (Hybrid)** accepted.  
2. Desktop strategy: **Playwright-first on Wayland** vs **switch daily session to X11**.  
3. Master language: **Python 3.13** accepted.  
4. n8n on same Pi vs secondary host.  
5. Cloud provider preference for specialists (Gemini already in Mark vs multi-provider via LiteLLM-style router).
