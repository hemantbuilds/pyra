# Phase 5c Implementation — PydanticAI + Research Agent

**Date:** 2026-11-10  
**Architecture:** Baseline v1.0 (unchanged decisions)  
**Status:** Implemented · offline suite green · live Ollama structured-output unreliable on qwen2.5:3b / gemma3:1b

---

## 1. Objective

Integrate **PydanticAI** behind the existing Agent Runtime and deliver the first AI specialist:

- **agent_id:** `research`
- **name:** Research Agent
- **output:** validated `ResearchReport`

## 2. Architecture inspected

Phase 5b Runtime (`SpecialistAgent`, `AgentRuntime`, `AgentBrokerSession`, Master `AGENT_*` intents) is preserved.

Flow implemented:

```text
Mark → Dot → Master → Agent Runtime → ResearchAgent (PydanticAI)
                                      → ModelGateway → Ollama / TestModel
                                      → AgentBrokerSession → BrokerClient → Device Broker
                                      → AgentResult → Master → Dot
```

## 3. Design

| Piece | Role |
|---|---|
| `PydanticAISpecialistAgent` | Adapter implementing `SpecialistAgent` |
| `ResearchAgent` | First specialist |
| `ResearchReport` | Structured output schema |
| `ModelGateway.resolve_agent_model` | Provider/model resolution |
| `ProviderSettings` | Non-secret config (env) |
| Deterministic `echo` / `broker_probe` | Unchanged; no PydanticAI dependency for their execution |

## 4. Dependencies

| Package | Version |
|---|---|
| Python | 3.13.5 |
| pydantic | 2.14.3 |
| fastapi | 0.162.2 |
| pydantic-ai-slim[openai] | **2.66.0** (pinned) |
| httpx | 0.28.1 |

Installed `pydantic-ai-slim[openai]` (not full `pydantic-ai`) to avoid MCP/Anthropic/Google extras. Ollama uses OpenAI-compatible client.

`pip check`: clean.

## 5. ModelGateway

- Default provider: **ollama** (`OLLAMA_HOST`, `OLLAMA_MODEL`).
- Optional: `openai` (disabled by default; key from `OPENAI_API_KEY` env only).
- `test` provider + `set_override_model()` for offline tests.
- Provider failures → controlled `ProviderError` → AgentResult `BLOCKED`/`FAILED` (Master does not crash).

## 6. Research Agent

- Allowlist (L0): `get_system_info`, `get_platform_info`, `get_available_toolchains`, `get_installed_tool_versions`, `list_directory`, `read_text_file`.
- Instructions forbid inventing hardware identity / fabricating tool results.
- Maps `ResearchReport` → `AgentResult.result`.

## 7. Master integration

Phrases: `run research agent`, `research this…`, `ask research agent…`  
Registry: `GET /v1/agents` includes `research`.

## 8. Security

All Phase 5b invariants retained: Broker authority, L1 ceiling, no MCP internal path, no L2/L3, secrets not in contracts/logs/results.

## 9. Known limitations

- Small local models (`qwen2.5:3b`, `gemma3:1b`) failed PydanticAI structured-output retries in live smoke; offline **TestModel** path is the validated integration.
- Single specialist only (by design).
- No LangGraph / LiteLLM / MCP SDK / L2–L3.

## 10. Future work

- Phase 5d ModelGateway evaluation (direct vs conditional LiteLLM).
- Stronger local models or PromptedOutput tuning for Pi.
- Phase 5a MCP SDK PoC (external only).
- Phase 6 Engineering OS L2.
