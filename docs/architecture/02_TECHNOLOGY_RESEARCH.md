# Document 2 — Technology Research

Sources consulted include official docs/repos for MCP, ACP, OpenClaw, OpenHands, n8n, Ollama community RPi benchmarks, and multi-agent framework comparisons (2025–2026). This is research for selection, not endorsement of every project.

---

## 1. Protocol layer

### 1.1 MCP — Model Context Protocol

| Attribute | Detail |
|---|---|
| Spec | https://modelcontextprotocol.io/specification/2026-07-28 |
| Role | Tools, resources, prompts between hosts and servers |
| Transports | stdio; Streamable HTTP (SSE legacy) |
| Auth (HTTP) | OAuth 2.1 optional; stdio uses env credentials |
| License | Spec open; SDKs vary (official TS/Python SDKs) |
| ARM64 | Client/server are ordinary processes — fine on Pi |
| Fit for PYRA | **Primary tool bus** for device, lab, project, n8n |

**Must use:** tools with JSON Schema; treat tool descriptions as untrusted unless server is first-party; human consent for sensitive tools; validate outputs before feeding models.

**Do not use MCP as:** multi-agent orchestrator, project database, or permission authority (permission lives in Device Broker).

### 1.2 ACP — Agent Client Protocol

| Attribute | Detail |
|---|---|
| Site | https://agentclientprotocol.com |
| Repo | https://github.com/agentclientprotocol/agent-client-protocol |
| Role | IDE/client ↔ coding agent (JSON-RPC); session new/resume/prompt/cancel |
| Ecosystem | Zed, JetBrains, Gemini CLI, OpenCode, Copilot, etc. |
| Fit for PYRA | **Coding specialist sessions** with resume — not ops/mail/hardware bus |

**Clear distinction:** ACP = coding agent sessions. MCP = tools. Master orchestrator = custom.

### 1.3 OpenAI-compatible HTTP

De facto lingua franca for Ollama, Groq, OpenRouter, vLLM, Mark `providers/llm_openai.py`. Master and specialists should speak this for model I/O.

---

## 2. Agent platforms

### 2.1 OpenClaw

| Attribute | Detail |
|---|---|
| Docs | https://docs.openclaw.ai ; architecture https://github.com/openclaw/openclaw/blob/main/docs/concepts/architecture.md |
| License | MIT (per project docs) |
| Architecture | Long-lived **Gateway** (WS+HTTP), channels, sessions, agent runtime, nodes, approvals, MCP registry, ACP hosting |
| Strengths | Mature gateway, multi-channel, session model, approvals, MCP/ACP bridges, plugin SDK |
| Weaknesses for PYRA | Oriented to chat-channel assistants; overlaps Mark’s face; unknown steady RAM with Mark+Ollama on 8 GB; embedded engineering not native; Node/TS weight likely |
| ARM64 | Community Pi guides exist; not verified on this host |
| Verdict | **Inspiration + optional later subsystem** — **not** foundation (see Alt B rejection in Doc 3) |

Patterns to steal: idempotent agent requests, approval events, session persistence, MCP client registry, loopback-default bind.

### 2.2 OpenHands

| Attribute | Detail |
|---|---|
| Docs | https://docs.openhands.dev |
| Architecture | SDK / tools / workspace / Agent Server; Docker sandbox opt-in in V1; first-class MCP; ACP examples |
| Strengths | Serious coding agent, sandboxes, MCP, conversation persistence |
| Weaknesses for PYRA | Heavy for always-on Pi; Docker sandboxes compete for RAM; not a Project OS for hardware bring-up |
| Verdict | **Optional coding specialist runtime (Phase 8)** — not Master |

### 2.3 Multi-agent frameworks

| Framework | Repo / license | Pros | Cons on Pi | Verdict |
|---|---|---|---|---|
| **LangGraph** | LangChain org; MIT | Explicit graphs, checkpoints, human-in-loop | Extra deps; learning curve | **Evaluate Phase 4** for engineering pipelines |
| **CrewAI** | CrewAI; MIT | Fast role/task DX | High Python overhead in community benches | **Reject for core** |
| **AutoGen** | Microsoft; MIT | Group chat agents | Maintenance mode; successor elsewhere | **Reject for new work** |
| **PydanticAI** | Pydantic; MIT | Typed outputs, DI, testability | Not a full orchestrator | **Use for contracts / specialist agents** |
| **Semantic Kernel** | Microsoft | Enterprise plugins | Heavier; less needed | Skip |
| **LlamaIndex** | LlamaIndex | RAG pipelines | Only if doc corpora demand | Optional research agent RAG later |
| **LiteLLM** | BerriAI | Multi-provider router | Another service | **Accept pattern**; implement thin router first, adopt lib if needed |
| **Agno** | agno-agi | Fast agent microbench claims | Newer; less protocol alignment | Watch list |

**Selection:** Custom Master orchestrator + **Pydantic** models for I/O contracts. Consider **LangGraph** only when durable multi-step engineering graphs outgrow hand-rolled state machines. Avoid stacking CrewAI+LangGraph+OpenClaw.

---

## 3. Local inference (Ollama)

| Attribute | Detail |
|---|---|
| Site | https://ollama.com |
| This host | Installed, active, models `qwen2.5:3b`, `gemma3:1b` |
| Features needed | Tool calling, `/api/chat`, keep_alive, OpenAI compat |
| ARM64 | First-class via llama.cpp |

### Model guidance for Master (community + research; **not** measured here)

| Model | Typical role | Notes from public RPi5 reports |
|---|---|---|
| qwen2.5:1.5b | Fast intent / demo | Often unreliable tool calling |
| **qwen2.5:3b** | Candidate Master | Present on disk; mixed reports (mediocre→good); ~5–6 t/s class |
| qwen2.5:7b | More reliable tools | Slow (~tens of seconds); RAM tight with Mark+Cursor |
| gemma3:1b | Present | Fast; tool calling weaker unless specialized variant |
| Hailo LLM adapters | Experimental | Do **not** assume general Ollama GGUF on Hailo-8 |

**Master design implication:** Local model does **intent, routing, short plans, status**. Validate JSON with Pydantic. Escalate complex reasoning to cloud. Pin model with `keep_alive`. Prewarm. Cap tool count (Mark LVI measurements apply).

**Phase 0 required benchmark (owner-approved):** RSS while loaded, t/s, structured tool-call success rate on a fixed 20-prompt suite.

---

## 4. Automation — n8n

| Attribute | Detail |
|---|---|
| Site | https://n8n.io ; MCP docs https://docs.n8n.io/build/integrate-ai/mcp-servers |
| License | Sustainable Use License (not OSI MIT) — OK for personal; review if commercializing |
| Capabilities | Workflows, webhooks, cron, credentials, retries, MCP Server Trigger, instance MCP, AI Agent node |
| Deploy | Docker + Postgres typical; **Compose plugin missing on this host** |
| Fit | Deterministic personal/ops integrations |

**Pattern:** Master discovers/executes approved workflows via MCP or webhook; n8n never becomes the orchestrator of engineering agents.

---

## 5. Browser / desktop automation

| Tech | Role | Wayland on this Pi |
|---|---|---|
| **Playwright** | Agent browser, forms, downloads | Works (in-browser); preferred Phase 3 |
| Mark `browser_control` | Existing Playwright wrapper | Reuse as reference / bridge |
| pyautogui | OS input | **Unreliable on Wayland** |
| grim/slurp | Screenshots | Available |
| xdg-desktop-portal / wlr | Permissioned capture | Partial |
| wayvnc | Remote view | Active; observation channel |
| ydotool/wtype | Wayland typing | Not installed; investigate later |
| X11 session | Full classic automation | Optional operator choice |

**Browser-use / Computer-Use frameworks:** useful research; prefer Playwright + explicit approval for Phase 3 to limit dependency surface.

---

## 6. Embedded engineering tooling (integration targets)

| Domain | Tools to integrate (Phase 7+) |
|---|---|
| Build | CMake, west, idf.py, PlatformIO, Make |
| Flash/debug | OpenOCD, pyOCD, probe-rs, esptool |
| Serial | pyserial / `tio` / `minicom` |
| RTOS/SDK | Zephyr, ESP-IDF, STM32Cube, MCUXpresso exports |
| EDA | KiCad CLI (schematic/PCB export, ERC/DRC where available) — **never trust AI schematics without review** |
| Analysis | compiler logs, static analyzers (clang-tidy, cppcheck) |

None of these replace electrical verification.

---

## 7. Observability / workflow engines

| Tech | Verdict |
|---|---|
| OpenTelemetry | **Accept** for Master/broker spans in Phase 9 hardening |
| Temporal | Powerful durable workflows; **too heavy** for Pi core — reject for v1 |
| systemd | **Accept** as primary process supervisor |

---

## 8. Storage

| Tech | Verdict |
|---|---|
| Filesystem project trees | **Required** for artifacts/repos |
| SQLite | **Required** for registry, tasks, audit — zero daemon |
| PostgreSQL | n8n dependency if self-hosted classic stack; not for Project OS core |
| Vector DB | Optional later for datasheet corpora; not for task graphs |

---

## 9. Prior-plan tech statements (preview)

Full reclassification in Doc 14. Headline: MCP/ACP/n8n/hybrid local-cloud **accept**; OpenClaw-as-inspiration **accept**; Hailo-as-LLM **reject**; Wayland-full-control **reject**; “Ollama 3B is enough for Master routing” **investigate further with benchmarks**.
