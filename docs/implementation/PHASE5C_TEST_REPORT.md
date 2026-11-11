# Phase 5c Test Report

**Date:** 2026-11-10  
**Host:** Raspberry Pi 5 · ARM64 · Debian  
**Python:** 3.13.5  
**Dependencies:** pydantic 2.14.3 · pydantic-ai-slim 2.66.0 · fastapi 0.162.2  

## Commands

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

## Final automated results

| Metric | Value |
|---|---|
| **Passed** | **132** |
| Failed | 0 |
| Skipped | 0 |
| `pip check` | No broken requirements |

### Suites

| Suite | Role |
|---|---|
| `tests/agent_runtime` | Phase 5b regression + PydanticAI adapter |
| `tests/research_agent` | ResearchReport + Research Agent scenarios |
| `tests/model_gateway` | Provider config / errors / secrets |
| `tests/master` | Dot/Master intents + regression |
| `tests/project_os` / `device_broker` / `engineering_os` | Phase 0–4 regression |

## Live provider validation

| Check | Result |
|---|---|
| `ollama list` / reachable | **PASS** (`qwen2.5:3b`, `gemma3:1b` present) |
| Full ResearchAgent via Ollama | **FAIL** — Runtime timeout 120s (tools + structured output too heavy on 3b) |
| Minimal PydanticAI `ResearchReport` via Ollama | **FAIL** — `UnexpectedModelBehavior` output retries exhausted (gemma3:1b ~71s, qwen2.5:3b ~209s) |
| Offline TestModel ResearchAgent | **PASS** (suite) |

**Conclusion:** Integration is proven with **deterministic TestModel**. Live small-model structured output on this Pi is **not** production-ready yet — recorded honestly, not claimed passed.

## Performance (indicative)

| Measurement | Value |
|---|---|
| Offline suite wall time | ~4.1 s for 132 tests |
| Live ResearchAgent attempt peak RSS | ~90 MB (process maxrss) |
| Live ResearchAgent latency | 299 s → timeout |
| Production latency budget | **NOT ESTABLISHED** from mocked models |

## Acceptance criteria (P5C-01 … P5C-30)

| ID | Result | Evidence |
|---|---|---|
| P5C-01 | **PASS** | pydantic-ai-slim==2.66.0 pinned; pip check clean |
| P5C-02 | **PASS** | 5b tests in 132 green |
| P5C-03 | **PASS** | `PydanticAISpecialistAgent` + adapter tests |
| P5C-04 | **PASS** | echo/broker_probe still native |
| P5C-05 | **PASS** | `ModelGateway.resolve_agent_model` |
| P5C-06 | **PASS** | env keys; secret tests |
| P5C-07 | **PASS** | provider unavailable → BLOCKED; Master continues |
| P5C-08 | **PASS** | research in registry |
| P5C-09 | **PASS** | AgentTask reused |
| P5C-10 | **PASS** | ResearchReport validation tests |
| P5C-11 | **PASS** | TestModel execution |
| P5C-12 | **PASS** | scenario D insufficient MCU |
| P5C-13 | **PASS** | scenario B/E |
| P5C-14 | **PASS** | tools via AgentBrokerSession only |
| P5C-15 | **PASS** | Broker denial tests |
| P5C-16 | **PASS** | L0 research / L1 ceiling |
| P5C-17 | **PASS** | identity + level tests |
| P5C-18 | **PASS** | runtime timeout path (live + 5b timeout test) |
| P5C-19 | **PASS** | invalid output / schema tests |
| P5C-20 | **PASS** | Master run research |
| P5C-21 | **PASS** | evidence.agent_result |
| P5C-22 | **PASS** | Dot path test |
| P5C-23 | **PASS** | full regression 132 |
| P5C-24 | **PASS** | concurrent isolation test |
| P5C-25 | **PASS** | secret-handling tests |
| P5C-26 | **PASS** | no MCP internal; slim without mcp extra |
| P5C-27 | **PASS** | no LangGraph/LiteLLM/CrewAI |
| P5C-28 | **PASS** | no L2/L3/hardware writes |
| P5C-29 | **PASS** | this doc + implementation doc |
| P5C-30 | **PASS** | reproducible commands above |

## Security invariants S1–S12

All **preserved** under automated tests. Live hardware flash/serial **not exercised** (out of scope).

## Unresolved

- Live Ollama structured ResearchReport on 1b/3b models.
- Stronger local model recommendation deferred to ops/5d.
