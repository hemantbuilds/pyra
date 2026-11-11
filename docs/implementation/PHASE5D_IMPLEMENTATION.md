# Phase 5d Implementation — ModelGateway Evaluation & Validation

**Date:** 2026-11-10  
**Architecture:** Baseline v1.0 (unchanged decisions)  
**Verdict:** **COMPLETE WITH LIMITATIONS**

---

## 1. Objective

Strengthen and validate ModelGateway so Master and PydanticAI specialists have a reliable, measurable model execution layer — without OpenRouter, cloud keys, LiteLLM migration, or architecture redesign.

## 2. Audit findings

See [`PHASE5D_AUDIT.md`](PHASE5D_AUDIT.md).

Pre-5d gaps:

- Gateway resolved models but did not own invoke/retry/cancel/metadata.
- Cancellation was only Runtime thread timeout (not cooperative).
- Structured-output failures were not characterized by format type.
- No model inventory API.

## 3. Model inventory (verified)

| Name | Params | Quant | Context | Ollama capabilities |
|---|---|---|---|---|
| `qwen2.5:3b` | 3.1B | Q4_K_M | 32768 | completion, **tools** |
| `gemma3:1b` | ~1.0B | Q4_K_M | 32768 | completion |

No models downloaded in this phase.

## 4. Changes implemented

| Change | Purpose |
|---|---|
| `master/invocation.py` | `CancellationToken`, `RetryPolicy`, `InvocationResult`, failure taxonomy |
| `ModelGateway.complete_text` / `complete_json` | Bounded timeout + retry + cancel + metadata |
| `list_ollama_models` / `model_available` | Inventory & availability |
| Settings `PYRA_GATEWAY_*` | Timeout / retries / num_predict |
| `ExecutionContext.cancel_token` | Cooperative cancel into specialists |
| Runtime preserves cancel tokens (no `model_dump` loss) | Cancel propagation |
| ResearchAgent: `NativeOutput` **only for OllamaModel** | Align with json_schema reliability on Pi |
| Adapter: cancel checks + `model_settings.timeout` | Reliability |

**Not introduced:** OpenRouter, LiteLLM, cloud providers, MCP, LangGraph, L2/L3.

## 5. Recommended configuration (Pi)

```bash
export OLLAMA_HOST=http://127.0.0.1:11434
export OLLAMA_MODEL=qwen2.5:3b          # preferred over gemma3:1b for tools/schema
export PYRA_GATEWAY_TIMEOUT_S=45
export PYRA_GATEWAY_MAX_RETRIES=1
export PYRA_GATEWAY_NUM_PREDICT=256
```

For structured JSON via gateway, prefer **JSON Schema** (`complete_json(..., json_schema=...)`) over `format="json"`.

## 6. LiteLLM decision

**Decision: Keep direct provider integrations. Defer LiteLLM SDK.**

Justification:

- Direct Ollama path is sufficient for current providers.
- LiteLLM would add dependency/ARM footprint without fixing small-model structured latency.
- Architecture already requires PYRA-owned ModelGateway regardless of backend.
- No measurable benefit on this Pi workload in 5d evidence.
- Proxy remains out of scope (ADR-003).

## 7. Known limitations

- `qwen2.5:3b` text ~4 tok/s; structured schema ~30–45s when it succeeds; often times out under load.
- `gemma3:1b` faster text (~9 tok/s) but weak/invalid structured schema compliance.
- Live PydanticAI ResearchAgent + tools remains heavy for these models.
- Cooperative cancel stops new gateway attempts; in-flight HTTP may still finish until socket timeout.
- Cloud / OpenRouter deferred.

## 8. Deferred

- OpenRouter / cloud providers.
- LiteLLM SDK adoption.
- Larger local models (manual ops).
- Streaming UX.
- Phase 6 Eng OS L2.
