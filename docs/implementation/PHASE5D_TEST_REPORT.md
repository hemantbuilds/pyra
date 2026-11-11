# Phase 5d Test Report — ModelGateway Evaluation

**Date:** 2026-11-10  
**Host:** Raspberry Pi 5 · ARM64  
**Python:** 3.13.5 · pydantic 2.14.3 · pydantic-ai-slim 2.66.0  

Raw benchmark data: [`phase5d_benchmark_raw.json`](phase5d_benchmark_raw.json)

---

## 1. Commands

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
```

## 2. Automated results (final)

| Metric | Value |
|---|---|
| **Passed** | **149** |
| Failed | 0 |
| Skipped | 0 |
| `pip check` | clean |

Includes new: invoke/retry/cancel, tool-calling, cancellation isolation, prior 0–5c regression.

---

## 3. Live inference benchmarks

**Method:** identical prompts; `num_predict=256`; temperature 0.1; timeout 50s; Ollama `/api/chat`; no unbounded retries.

### Capability matrix

| Capability | qwen2.5:3b | gemma3:1b |
|---|---|---|
| Connection | PASS | PASS |
| Basic text (A) | PASS (45.7s, ~3.9 tok/s) | PASS (28.7s, ~8.8 tok/s) |
| Embedded text (B) | PASS (20.8s, ~3.9 tok/s) | PASS (8.7s, ~8.8 tok/s) |
| Context bullets (D) | PASS (11.3s) | PASS (20.2s) |
| Structured `format=json` | FAIL (timeout 50s) | FAIL (JSON syntax/schema) |
| Structured **JSON Schema** | PASS once (~35s, schema valid) | FAIL (invalid/truncated) |
| Tool calling (OpenAI `/v1`) | PASS (requested `get_system_info`) | UNKNOWN / not advertised |
| Unavailable model | PASS (HTTP error handled) | — |
| Gateway `complete_json` under load | FAIL timeout after **2 attempts** (correct failure) | — |

### Notes

- Syntax-valid JSON ≠ schema-valid (gemma returned JSON that failed required fields).
- TTFT not separately instrumented (Ollama non-stream chat) — **NOT MEASURED**.
- Sample count: 1 run per cell (exploratory); not a production SLA.

---

## 4. Structured-output conclusions

| Cause area | Finding |
|---|---|
| Model capability | Dominant — 1b/3b struggle with unconstrained JSON |
| Ollama API | JSON Schema format more reliable than `format=json` for qwen |
| PydanticAI | TestModel offline PASS; NativeOutput used for live Ollama only |
| ModelGateway | Correctly reports timeout/validation with bounded retries |

---

## 5. Timeout / retry / cancellation (automated)

| Behaviour | Result |
|---|---|
| Success before timeout | PASS |
| Timeout + retry exhaustion | PASS |
| Auth not retried | PASS |
| Cancel before invoke | PASS |
| Cancel isolation (sibling continues) | PASS |
| Runtime → ResearchAgent cancel | PASS |
| Invalid JSON retry then success | PASS |

---

## 6. Tool-calling (automated + live probe)

| Test | Result |
|---|---|
| TestModel calls `get_system_info` via Broker | PASS |
| Unknown tool allowlist denial | PASS |
| L1 tool with L0 max → Broker deny | PASS |
| Live qwen tool_calls for `get_system_info` | PASS (HTTP 200) |

---

## 7. Resource notes

| Measurement | Value |
|---|---|
| Benchmark client peak RSS (indicative) | ~30–32 MB during chat |
| Ollama model memory | **separate process — not equated to PYRA RSS** |
| Automated suite wall time | ~5 s (149 tests) |

---

## 8. LiteLLM

**Decision: DEFER — keep direct integrations.** See implementation doc.

---

## 9. Acceptance checklist

| # | Criterion | Result |
|---|---|---|
| 1 | Gateway audited | **PASS** |
| 2 | Provider config documented | **PASS** |
| 3 | Models inventoried | **PASS** |
| 4 | Live inference benchmarked | **PASS** (with measured failures) |
| 5 | Structured-output measured | **PASS** |
| 6 | Pydantic validation tested | **PASS** |
| 7 | Tool-calling tested | **PASS** |
| 8 | Provider failures safe | **PASS** |
| 9 | Timeout tested | **PASS** |
| 10 | Cancellation explicitly tested | **PASS** |
| 11 | Retry bounded & tested | **PASS** |
| 12 | Concurrent isolation tested | **PASS** |
| 13 | Credentials validated | **PASS** |
| 14 | Runtime/Research still functional | **PASS** |
| 15 | LiteLLM decision documented | **PASS** |
| 16 | Pi resource notes | **PASS** (partial) |
| 17 | Regression green | **PASS** (149) |
| 18 | Docs updated | **PASS** |
| 19 | No OpenRouter / new cloud keys | **PASS** |
| 20 | No weakened security/architecture | **PASS** |

### Final verdict

**COMPLETE WITH LIMITATIONS** — ModelGateway reliability and tests are complete; installed 1b/3b models remain inadequate for reliable live structured specialist inference on this Pi.
