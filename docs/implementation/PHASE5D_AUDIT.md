# Phase 5d — Initial ModelGateway Audit (pre-implementation)

**Date:** 2026-11-10  
**Status:** Assessment complete before code changes

## 1. Current architecture

`ModelGateway` (`master/model_gateway.py`) owns:

- Deterministic + Ollama **intent classification** for Master.
- **`resolve_agent_model()`** for PydanticAI specialists (returns a PydanticAI `Model`).
- Provider status / override for tests.

`ProviderSettings` (`master/provider_config.py`) loads non-secret config from env.

PydanticAI specialists call `gateway.resolve_agent_model()` then `Agent.run_sync()` directly — **invocation, retries, and streaming are not owned by ModelGateway today**.

## 2. Supported providers

| Provider | Enabled by default | Notes |
|---|---|---|
| ollama | yes | `OLLAMA_HOST`, `OLLAMA_MODEL` |
| openai | no | needs `OPENAI_API_KEY` — **not used in 5d** |
| test | yes | TestModel for offline tests |

## 3. Model selection

- Default: `ProviderSettings.default_provider` (`PYRA_DEFAULT_PROVIDER` or `ollama`).
- Model name: `OLLAMA_MODEL` / per-provider default.
- Override: `set_override_model()` for tests.
- Per-agent: `ResearchAgent(provider=, model_name=)` optional kwargs.

## 4. How PydanticAI accesses the gateway

`PydanticAISpecialistAgent._resolve_model()` → `ModelGateway.resolve_agent_model()` → build `Agent` → `run_sync`.

No gateway-level invoke wrapper around the PydanticAI run.

## 5. Credentials / config

- Env only; `public_status()` never returns secret values.
- OpenAI key via `OPENAI_API_KEY` name only in status.

## 6. Timeouts / retries (current gaps)

| Layer | Behaviour |
|---|---|
| Intent HTTP | `SETTINGS.request_timeout_s` (45s) |
| Agent Runtime | ThreadPoolExecutor timeout on `agent.run` |
| ModelGateway | **No** invoke retry policy |
| PydanticAI | Own output retries (caused 5c live failures) |
| Cancellation | **Not** an explicit token; timeout ≠ cancel |

## 7. Error propagation

`ProviderError` → adapter maps to `BLOCKED`/`FAILED`. Intent path falls back to deterministic. Good for resolution; weak for mid-invoke failures.

## 8. Cancellation

No `CancellationToken`. Runtime timeout abandons the future but worker may continue until provider returns.

## 9. Existing tests

`tests/model_gateway/`, `tests/research_agent/`, adapter tests — cover config, secrets, TestModel path, provider unavailable. **Missing:** explicit cancel propagation, bounded gateway retries, structured-output gateway helpers, concurrency cancel isolation, model inventory checks.

## 10. Phase 5c known gaps

- Live Ollama structured output unreliable on qwen2.5:3b / gemma3:1b.
- Tool-calling + structured output too heavy on Pi small models.
- No measured gateway-owned invoke metrics.
- LiteLLM not evaluated with evidence.

## Installed models (verified)

| Name | Params | Quant | Context | Capabilities (ollama show) |
|---|---|---|---|---|
| qwen2.5:3b | 3.1B | Q4_K_M | 32768 | completion, **tools** |
| gemma3:1b | ~1.0B | Q4_K_M | 32768 | completion (no tools listed) |
