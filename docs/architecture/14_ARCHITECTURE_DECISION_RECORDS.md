# Document 14 — Architecture Decision Records & Prior-Plan Review

---

## A. Prior document review (`docs/PYRA_AGENT_TEAM_PLAN.md`)

| Prior recommendation | Classification | Why |
|---|---|---|
| Mark as face; Master as separate daemon | **Accept** | Confirmed by audit; avoids Qt/Live coupling |
| Evolve pukky into Master | **Accept with modifications** | Keep patterns; new service (not grow 336-line script in place) |
| Project OS under `~/PyraWork` | **Accept** | Needed; refined with SQLite+FS in Doc 6 |
| MCP as tool bus | **Accept** | Spec-aligned; don’t use as orchestrator |
| ACP for coding agents | **Accept** | Coding sessions only |
| n8n for deterministic automation | **Accept** | With license/RAM caveats |
| Specialist roster (systems/HW/FW/…) | **Accept with modifications** | Add explicit `project_mgr`, `testing`, `docs`; enforce manifests |
| Hybrid local/cloud | **Accept** | Required for Pi |
| Hailo for vision not chat | **Accept** | Matches hardware + pukky |
| Prefer X11 for full desktop | **Accept with modifications** | Valid option; **Playwright-first on Wayland** is default until user switches session |
| OpenClaw as reference stack | **Accept as inspiration** | Not foundation (Alt B rejected) |
| Option to point Mark providers at Master | **Investigate further** | Risk of tool-budget/latency issues; plugin HTTP preferred first |
| Lang-less “just use API agents” early | **Accept** | Phase 4 |
| Single doc as sufficient design | **Reject** | Replaced by this 14-doc package |
| Implied ease of Hailo-LLM path | **Reject** | Experimental only |
| Assume Compose/n8n ready | **Reject** | Compose plugin missing |
| “Unlimited projects” without storage model | **Accept with modifications** | Unlimited practical; SQLite registry |

---

## B. ADR log

### ADR-001 — Architecture Alternative C (Hybrid)

- **Status:** Proposed  
- **Context:** Need multi-agent OS + embedded + Mark face on Pi 8 GB.  
- **Decision:** Custom Master/Project OS/Device Broker; MCP/ACP/n8n reuse; Mark plugin.  
- **Alternatives:** A custom-everything; B OpenClaw-core.  
- **Consequences:** More design work upfront; better fit and control.

### ADR-002 — Master language Python 3.13

- **Status:** Proposed  
- **Context:** Host Python 3.13; Mark/pukky Python; MCP Python SDK.  
- **Decision:** Python FastAPI Master.  
- **Alternatives:** Node (not installed), Go.  
- **Consequences:** GIL/concurrency limits → process workers for heavy tasks.

### ADR-003 — Project truth in SQLite + filesystem

- **Status:** Proposed  
- **Decision:** See Doc 6.  
- **Alternatives:** Postgres-only; chat-memory-only; pure JSON.  

### ADR-004 — Device Broker enforces permissions, not the LLM

- **Status:** Proposed  
- **Decision:** Levels 0–3 in Broker; Mark confirm for ≥2.  
- **Consequences:** Agents cannot self-elevate via prompt.

### ADR-005 — Playwright-first desktop/web; X11 optional

- **Status:** Proposed  
- **Context:** labwc Wayland; missing xdotool/ydotool.  
- **Decision:** Capability matrix; Null/X11/Playwright backends.  

### ADR-006 — n8n is not the brain

- **Status:** Proposed  
- **Decision:** MCP/webhooks only for deterministic ops.  

### ADR-007 — ACP is not the universal agent bus

- **Status:** Proposed  
- **Decision:** ACP for coding agent sessions; Master orchestrates.  

### ADR-008 — Hailo optional perception

- **Status:** Proposed  
- **Decision:** Core runs without Hailo; lab tools use HEFs.  

### ADR-009 — Avoid CrewAI / AutoGen for core

- **Status:** Proposed  
- **Decision:** Pydantic contracts + custom orchestrator; evaluate LangGraph later.  

### ADR-010 — No NASA cFS

- **Status:** Accepted (assignment constraint)

### ADR-011 — Mark integration via plugin, not main.py fork

- **Status:** Proposed  

### ADR-012 — Single foreground interactive project

- **Status:** Proposed  
- **Decision:** One active interactive project; detachable background jobs allowed with governor.  

---

## C. Open questions for owner review

1. Confirm Architecture **C**.  
2. Desktop: stay Wayland (Playwright-first) or switch to X11 session?  
3. n8n on this Pi or another host?  
4. Preferred cloud ladder for specialists (Gemini-first vs multi-provider)?  
5. Approve Phase 0 actions: Mark venv repair, Compose plugin, Ollama benchmarks?
