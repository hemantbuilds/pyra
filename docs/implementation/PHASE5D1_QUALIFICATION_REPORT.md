# Phase 5d.1 — Qualification Report

**Date:** 2026-11-10  
**Host:** Raspberry Pi (ARM64) · Ollama local  
**Models installed (no downloads):** `qwen2.5:3b`, `gemma3:1b`  
**Automated suite:** **170 passed / 0 failed / 0 skipped**  
**Raw benchmarks:** [`phase5d1_benchmark_raw.json`](phase5d1_benchmark_raw.json)  
**Hardening notes:** [`PHASE5D1_HARDENING.md`](PHASE5D1_HARDENING.md)

---

## 1. Initial audit findings

- Gateway invoke/retry/cancel existed from Phase 5d but lacked overall deadline, mid-flight HTTP abort, and Pydantic-authoritative structured validation.
- Benchmarks were single-sample.
- Live tool-calling evidence was thin (one probe).
- LiteLLM correctly deferred; architecture ownership intact.

## 2. Fixes implemented

See hardening doc. Summary: overall timeout budget, cancellable HTTP worker+client close, Pydantic validation on `complete_json`, status-code failure taxonomy, secret redaction, capability profiles, always-record `broker_calls` evidence (including empty).

## 3. Files created / modified (5d.1)

**Created**
- `agent-os/master/model_profiles.py`
- `tests/model_gateway/test_hardening_5d1.py`
- `scripts/phase5d1_benchmark.py`
- `docs/implementation/PHASE5D1_GAP_ANALYSIS.md`
- `docs/implementation/PHASE5D1_HARDENING.md`
- `docs/implementation/PHASE5D1_QUALIFICATION_REPORT.md`
- `docs/implementation/phase5d1_benchmark_raw.json`

**Modified**
- `agent-os/master/invocation.py` — QualificationStatus, SERVER_ERROR, redact, remaining_timeout
- `agent-os/master/model_gateway.py` — budget, cancel HTTP, pydantic validate, profiles in status
- `agent-os/agent_runtime/agents/research.py` — always emit broker_calls evidence
- `tests/research_agent/test_tool_calling.py` — isolation / deny / invalid-args cases

## 4. Tests added

Hardening suite (`test_hardening_5d1.py`): provider/model failure paths already covered in 5d; plus overall budget, 429/5xx, empty/invalid JSON, schema mismatch, Pydantic authority, mid-flight cancel+HTTP close, concurrency, credential redaction, profiles.

Research tool tests: invalid args, project isolation, disallowed-tool Broker denial.

## 5. Exact test commands

```bash
cd ~/pyra
agent-os/.venv/bin/pip check

PYDANTIC_AI_NO_BANNER=1 agent-os/.venv/bin/python -m pytest \
  tests/agent_runtime \
  tests/master \
  tests/project_os \
  tests/device_broker \
  tests/engineering_os \
  tests/model_gateway \
  tests/research_agent \
  -q

PYTHONUNBUFFERED=1 PYDANTIC_AI_NO_BANNER=1 \
  agent-os/.venv/bin/python scripts/phase5d1_benchmark.py
```

## 6. Automated counts

| Metric | Count |
|---|---|
| Passed | **170** |
| Failed | **0** |
| Skipped | **0** |
| `pip check` | clean |

## 7. Repeated model benchmarks

**Env:** gateway_timeout_s=60, max_retries=1, num_predict=128, temperature=0.1, non-stream `/api/chat`.  
**TTFT:** not measured (non-stream). Sample sizes are exploratory — not statistical SLAs.

### qwen2.5:3b

| Mode | n | Success | Median latency | Notes |
|---|---|---|---|---|
| Basic text | 5 | 5/5 | 5.815 s | tok/s ≈ 3.1–3.7 |
| Native `format=json` | 10 | 10/10 | 10.705 s | Simple StrictQualOut fields |
| JSON Schema format | 10 | 10/10 | 10.534 s | Same schema |
| Schema + Pydantic | 10 | 10/10 | 10.274 s | Validation authoritative |
| Cancel mid-flight | 1 | cancelled | 1.339 s | `clients_closed=1` |

### gemma3:1b

| Mode | n | Success | Median latency | Notes |
|---|---|---|---|---|
| Basic text | 5 | 5/5 | 3.283 s | tok/s ≈ 8.3–8.7; **max 47.9 s** |
| Native JSON | 10 | 10/10 | 9.183 s | Simple schema only |
| JSON Schema | 10 | 10/10 | 9.218 s | Simple schema only |
| Schema + Pydantic | 10 | 10/10 | 9.347 s | Simple schema only |
| Cancel mid-flight | 1 | cancelled | 1.340 s | `clients_closed=1` |

**Restriction:** These structured passes use a **3-field** schema. They do **not** re-qualify complex `ResearchReport` fidelity under tool-use (Phase 5d showed gemma failing richer schemas).

## 8. Cancellation evidence

| Layer | Result |
|---|---|
| Caller cancel before invoke | PASS (automated) |
| Mid-flight HTTP client close | PASS — abort ≪ timeout; local slow-server test + live cancel ~1.3 s |
| Sibling request isolation | PASS |
| Provider-side generation stopped | **NOT CLAIMED** — Ollama may continue after disconnect |

## 9. Structured-output qualification

| Model | Simple schema (5d.1) | Complex ResearchReport+tools |
|---|---|---|
| qwen2.5:3b | **QUALIFIED WITH RESTRICTIONS** (simple schema n=10) | **NOT QUALIFIED** as safety dependency |
| gemma3:1b | **QUALIFIED WITH RESTRICTIONS** (simple schema n=10; cold latency variance) | **NOT QUALIFIED** (historical 5d failures; not re-proven complex) |

Gateway behaviour: malformed / empty / schema-invalid → `VALIDATION` failure; no silent success.

## 10. Tool-calling qualification

| Path | Result |
|---|---|
| TestModel → AgentBrokerSession → Broker → `get_system_info` | **QUALIFIED** (automated) |
| Unknown / disallowed / L0-cap denial | **QUALIFIED** (automated) |
| Live qwen ResearchAgent ×5 must-call prompt | **NOT QUALIFIED** — 0/5 Broker-mediated; model completed while **skipping** tools and summarising as if tools ran |
| Live diagnostic wrap of `BrokerClient.call` | `client_calls=[]` while status COMPLETED |

**Invariant preserved:** when tools *are* invoked, they still pass only through Broker. Models cannot escalate or bypass policy. Hallucinated tool success is a **model** failure, not a Broker bypass.

## 11. Security qualification

| Check | Result |
|---|---|
| API keys absent from public status / redacted errors | QUALIFIED |
| Credentials not in AgentTask/Result | QUALIFIED |
| Tool path Broker-mediated | QUALIFIED |
| Agents cannot raise max_level / change project_id via session | QUALIFIED |
| L2/L3 unavailable | QUALIFIED (unchanged) |
| Model output cannot authorize ops | QUALIFIED (Broker policy authoritative) |

## 12. Performance (Pi)

| Measurement | Before | After bench |
|---|---|---|
| Benchmark process RSS | ~42 MB | ~104 MB |
| Ollama process RSS | ~24 MB (idle tags) | ~23 MB (model weights via runner; separate from gateway) |

Do not equate ModelGateway RSS with Ollama model memory. Concurrent mock-provider tests pass; live concurrency under dual-model load was not stress-qualified beyond cancel isolation.

**Configured max request duration:** `gateway_timeout_s` default **45 s** (bench used 60 s).

## 13. Unfixable / contained limitations

1. Ollama may continue generation after client cancel (provider-side).
2. Small local models may skip tools and hallucinate tool results.
3. Structured reliability is schema-complexity dependent; simple ≠ ResearchReport.
4. Warm vs cold latency variance (gemma max ≃48 s in basic n=5).
5. TTFT not measured on non-stream chat.
6. Sample sizes are small; not production SLAs.

## 14. Model capability matrix

| Capability | qwen2.5:3b | gemma3:1b |
|---|---|---|
| Basic inference | QUALIFIED | QUALIFIED WITH RESTRICTIONS |
| Structured JSON (simple) | QUALIFIED WITH RESTRICTIONS | QUALIFIED WITH RESTRICTIONS |
| JSON Schema (simple) | QUALIFIED WITH RESTRICTIONS | QUALIFIED WITH RESTRICTIONS |
| Pydantic simple schema | QUALIFIED WITH RESTRICTIONS | QUALIFIED WITH RESTRICTIONS |
| Tool calling (live Broker) | NOT QUALIFIED | NOT TESTED |
| Tool calling (TestModel/Broker) | QUALIFIED (framework) | QUALIFIED (framework) |
| Multimodal | NOT TESTED | NOT TESTED |

## 15. Component qualification (Phase 6 gate axes)

| Area | Classification | Why sufficient / restricted for Phase 6 |
|---|---|---|
| ModelGateway core reliability | **QUALIFIED** | Deterministic failure taxonomy, budgets, tests green |
| Basic Ollama inference | **QUALIFIED** / **WITH RESTRICTIONS** (gemma latency) | Text path usable; not a safety authority |
| Structured output per model | **QUALIFIED WITH RESTRICTIONS** | Simple schemas only; must not drive safety-critical decisions |
| Tool calling per model (live) | **NOT QUALIFIED** | Must not be a hidden dependency |
| Cancellation | **QUALIFIED WITH RESTRICTIONS** | Client abort proven; provider-side may continue |
| Timeout handling | **QUALIFIED** | Overall budget; permanent errors not retried |
| Concurrency | **QUALIFIED** | Isolation tests; mock providers |
| Security | **QUALIFIED** | Broker/policy/redaction invariants hold |
| PydanticAI integration | **QUALIFIED** | TestModel regression + adapter paths pass |

## 16. Phase 6 entry-gate assessment

Gate criteria:

1. ModelGateway core reliability qualified — **yes**
2. Timeouts and bounded retries qualified — **yes**
3. Cancellation / concurrency qualified or limitations contained — **yes** (provider-side cancel documented)
4. Security invariants intact — **yes**
5. PydanticAI deterministic regression pass — **yes**
6. Tool execution Broker-mediated — **yes**
7. Structured-output limitations documented — **yes**
8. Engineering OS must not depend on unqualified model behaviour for deterministic/safety-critical ops — **required design constraint for Phase 6**

### Verdict

**READY FOR PHASE 6 WITH DOCUMENTED RESTRICTIONS**

Phase 6 may proceed because control-plane reliability (gateway, timeout, cancel isolation, security, Broker mediation, TestModel regression) is qualified. Live model tool-calling and complex structured fidelity remain **NOT QUALIFIED** and must not become hidden dependencies for permissions, builds, or hardware operations. Engineering OS workflows stay deterministic where safety is concerned; models are advisory under Broker/policy authority.
