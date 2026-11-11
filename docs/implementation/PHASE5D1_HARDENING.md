# Phase 5d.1 — ModelGateway Hardening

**Date:** 2026-11-10  
**Scope:** Hardening and qualification of the existing PYRA ModelGateway after Phase 5d.  
**Non-goals:** No OpenRouter, LiteLLM migration, LangGraph, architecture baseline changes, L2/L3, commits, or pushes.

## 1. Initial audit (pre-code)

See also [`PHASE5D1_GAP_ANALYSIS.md`](PHASE5D1_GAP_ANALYSIS.md).

| Area | Finding |
|---|---|
| ModelGateway | PYRA-owned; Ollama direct + optional OpenAI resolve; TestModel override for specialists |
| Invocation | `CancellationToken`, `RetryPolicy`, `InvocationResult` present from 5d |
| Structured output | JSON parse only; empty accepted as parse failure after retry; no Pydantic authority on gateway path |
| Cancel | Checked between attempts only; in-flight HTTP not aborted |
| Retry budget | Per-attempt `timeout_s` × retries could extend wall clock unboundedly relative to caller expectation |
| HTTP 5xx/429 | Partial string classification |
| Profiles | Documentation only |
| Device Broker | Still sole tool-execution authority via `AgentBrokerSession` |
| LiteLLM | Deferred in 5d — retained |

Installed models at audit: `qwen2.5:3b`, `gemma3:1b` (no additional downloads).

## 2. Fixes implemented

### 2.1 Overall timeout budget
- `timeout_s` / `gateway_timeout_s` is now a **total wall-clock deadline** for all attempts.
- Retries use `remaining_timeout(deadline)` and cannot reset the budget.
- `ModelGateway.max_request_duration_s()` exposes the configured maximum.
- Default max request duration: **45s** (`PYRA_GATEWAY_TIMEOUT_S`).

### 2.2 Cancellation + HTTP transport
- In-flight POST runs on a worker thread.
- Cancel closes the `httpx.Client` from the caller thread (best-effort client abort).
- `clients_closed` counted in result metadata.
- **Provider limitation documented:** Ollama may continue generation server-side after client disconnect. PYRA does not claim provider-side stop without evidence.

### 2.3 Structured-output hardening
- Empty structured content → `FailureKind.VALIDATION` (not success).
- Non-object JSON root rejected.
- Optional `pydantic_model=` on `complete_json` — **Pydantic validation is authoritative**.
- No fabricated values on validation failure; `data` remains `None` on failure.
- Extra fields are not retained in validated `data` (Pydantic default ignore).
- Bounded retries for transient validation only; permanent errors (AUTH, CANCELLED, MODEL/PROVIDER unavailable) not retried.

### 2.4 Failure classification
- HTTP status codes: 401/403 → AUTH, 404 → MODEL_UNAVAILABLE, 429 → RATE_LIMIT, ≥500 → SERVER_ERROR.
- `redact_error_text` strips Bearer / sk- / api_key style secrets from errors.
- `InvocationResult.to_public_dict` continues to filter secret metadata keys.

### 2.5 Model capability profiles
- New `master/model_profiles.py` with capability-specific `QualificationStatus`.
- Surfaced via `provider_status()["model_capability_profiles"]`.
- Profiles updated from live 5d.1 benchmark script (verified behaviour only).

## 3. Tests added

| File | Coverage |
|---|---|
| `tests/model_gateway/test_hardening_5d1.py` | Budget, 5xx/429, empty/invalid JSON, Pydantic reject/accept, cancel mid-flight HTTP close, concurrency isolation, redaction, profiles |
| `tests/research_agent/test_tool_calling.py` | Invalid args, project isolation, Broker deny for disallowed tool |

Existing 5d suites retained (invoke/retry/cancel, ResearchAgent TestModel path, runtime cancel isolation).

## 4. Benchmark harness

`scripts/phase5d1_benchmark.py` — repeated basic (≥5) and structured (≥10 per mode) trials; cancel probe; optional Broker-mediated tool path; RSS before/after for benchmark process vs Ollama PID.

Raw output: [`phase5d1_benchmark_raw.json`](phase5d1_benchmark_raw.json)

## 5. Live tool-calling finding (not a gateway defect)

Repeated live ResearchAgent runs (qwen2.5:3b, n=5) completed **without** calling `get_system_info` while producing summaries that claimed host inspection. Broker was never bypassed — the model simply skipped tools. ResearchAgent now **always** records `broker_calls` (including `[]`) so skipped mediation is visible in evidence.

TestModel Broker-mediated tool path remains the qualified deterministic regression.

## 6. Architectural invariants preserved

- ModelGateway remains PYRA-owned.
- PydanticAI remains the specialist framework.
- Agent Runtime ownership unchanged.
- Device Broker remains the only tool-execution authority.
- No Broker bypass, no permission escalation, no L2/L3.
- No new cloud providers or API-key requirements.
- No architecture baseline document redesign in this phase’s code path.
