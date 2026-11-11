# Development Log

## 2026-11-10 — Phase 0

- Audited `/home/hem/pyra`, Mark-LIII, pukkyAI.  
- Confirmed Dot does **not** exist yet; documented Mark→Dot→Master resolution.  
- No `agent-os/`, no `~/PyraWork`, no Master service.  
- Ollama up with `qwen2.5:3b` / `gemma3:1b`.  
- Started Phase 1 scaffold.

## 2026-11-10 — Phase 1 start

- Creating `agent-os/master` (FastAPI, contracts, Ollama gateway, router).  
- Creating in-process Dot router module.  
- Creating Mark plugin `pyra_dot`.  
- Venv + tests under `tests/master`.

## 2026-11-10 — Phase 1 complete

- Flow: Mark plugin → `/dot/v1/interact` → Master orchestrator → capability stubs.  
- Deterministic intent preferred for clear phrases (Pi latency); Ollama for ambiguous.  
- Hardware bring-up intent registered as stub (no Arduino hardcode; awaits Device Broker).  
- Project intents return Phase-2 stub.  
- Tests: 14 passed. Live smoke against Ollama health OK.  
- Next: Phase 2 Project OS (`~/PyraWork`, create/list/switch/continue/checkpoints).

## 2026-11-10 — Phase 2 complete

- Replaced `project_os_stub` with real `agent-os/project_os` (SQLite + `~/PyraWork` FS trees).  
- Master: `project_service` singleton, `project_handlers`, expanded `IntentKind` + deterministic routes.  
- Capabilities registry now maps project/task/checkpoint intents to `project_os`.  
- Isolation: all reads/writes scoped by `project_id`; bounded `context_pack`.  
- Checkpoints store structured snapshots (project + tasks + memory); restore transactional.  
- Active project in `meta.active_project_id` survives reopen.  
- API: `GET /v1/projects`, `GET /v1/projects/active/context`.  
- SQLite `check_same_thread=False` + `RLock` for FastAPI worker threads.  
- Tests: **26 passed** (`tests/master` + `tests/project_os`).  
- Docs: `PROJECT_OS.md`, status / test results / known issues updated.  
- **Not started:** Device Broker, MCP hardware tools, Engineering OS (Phase 3+).  
- No git push.

## 2026-11-10 — Phase 3 complete

- Implemented `agent-os/device_broker/` with L0/L1 permissions, path jail, command allowlist, audit SQLite, secret redaction.  
- MCP stdio server (`python -m device_broker`) + Master in-process client (same core).  
- HTTP: `GET /broker/v1/tools`, `POST /broker/v1/call`.  
- Project OS supplies active workspace roots; no second project registry.  
- Master capability `device_broker` + deterministic intents for workspace/host phrases.  
- L2/L3 / flash / serial I/O / Engineering OS explicitly out of scope.  
- Tests: **45 passed** (device_broker + master + project_os).  
- Docs: `DEVICE_BROKER_PLAN.md`, `DEVICE_BROKER.md`, status/test/issues updated.  
- No git push. Waiting for review before Phase 4.

## 2026-11-10 — Phase 4 complete

- Added `agent-os/engineering_os/` (discovery, identify, toolchain, report, platform profiles).  
- Device Broker L0 tools: `enumerate_usb_devices`, `enumerate_serial_devices`, `enumerate_debug_probes`.  
- Master capability `engineering_os` replaces bring-up stub for discovery; flash still forbidden.  
- Deterministic phrases: “check the devices connected…”, bring-up language → discovery-only.  
- Project reports saved via Broker L1 into `projects/<id>/reports/`.  
- Live discovery on host saw `/dev/ttyACM0` Arduino Uno R3 (probable) + onboard ttyAMA unknowns.  
- Tests: **63 passed**. No git push. Waiting for review before Phase 5.

## 2026-11-10 — Architecture freeze (docs only)

- Created [`docs/architecture/PYRA_ARCHITECTURE_BASELINE.md`](../architecture/PYRA_ARCHITECTURE_BASELINE.md) v1.0.  
- Five correction ADRs ACCEPTED (`technology-adoption/ADRS_ARCHITECTURE_CORRECTIONS.md`).  
- Technology-adoption package + architecture index reconciled (BrokerClient ≠ MCP-internal; LiteLLM conditional; etc.).  
- Freeze review: [`ARCHITECTURE_FREEZE_REVIEW.md`](../architecture/ARCHITECTURE_FREEZE_REVIEW.md).  
- **No** Phase 5 code, dependency, or commit/push in this step.

## 2026-11-10 — Phase 5b complete (Agent Runtime foundation)

- Added `agent-os/agent_runtime/` (registry, contracts, lifecycle, `AgentBrokerSession`).  
- Reused existing `device_broker.client.BrokerClient` (no MCP internal path; no new DB; no PydanticAI/LangGraph).  
- Built-in deterministic agents: `echo`, `broker_probe` (L0 `get_system_info`).  
- Master capability `agent_runtime` + intents `AGENT_LIST` / `AGENT_RUN`; Dot path unchanged.  
- HTTP: `GET /v1/agents`, `POST /v1/agents/run`.  
- Tests: **93 passed** (agent_runtime + master + project_os + device_broker + engineering_os).  
- Docs: `AGENT_RUNTIME.md`, `PHASE5B_TEST_REPORT.md`; mapping + baseline status updated.  
- No git commit/push. Phase 5c (PydanticAI specialists) not started.

## 2026-11-10 — Phase 5c complete (PydanticAI + Research Agent)

- Dependency: `pydantic-ai-slim[openai]==2.66.0` (no MCP extra); pydantic 2.14.3 unchanged; `pip check` clean.  
- Adapter: `agent_runtime/pydantic_adapter.py`; specialist `research` + `ResearchReport`.  
- ModelGateway: `resolve_agent_model` / `ProviderSettings` (ollama default; openai optional via env).  
- Master: research intents; registry lists `research`.  
- Tests: **132 passed** (incl. research_agent + model_gateway + full 0–5b regression).  
- Live Ollama structured output on qwen2.5:3b/gemma3:1b: attempted, **failed** (timeout/retries) — offline TestModel is validated path.  
- Docs: `PHASE5C_IMPLEMENTATION.md`, `PHASE5C_TEST_REPORT.md`. No commit/push.

## 2026-11-10 — Phase 5d complete (ModelGateway evaluation)

- Audited gateway; added `invocation.py` (cancel/retry/metadata) + `complete_text`/`complete_json`/`list_ollama_models`.  
- Benchmarked `qwen2.5:3b` / `gemma3:1b` (text OK; structured unreliable; schema better than format=json for qwen).  
- ResearchAgent: NativeOutput only for OllamaModel; TestModel path unchanged.  
- LiteLLM decision: **defer** — keep direct providers. No OpenRouter/cloud.  
- Tests: **149 passed**. Docs: `PHASE5D_*`, audit, benchmark JSON. No commit/push.
