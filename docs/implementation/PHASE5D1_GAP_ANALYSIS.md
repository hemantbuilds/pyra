# Phase 5d.1 — Gap Analysis (pre-implementation)

**Date:** 2026-11-10  
**Models verified present:** `qwen2.5:3b`, `gemma3:1b`

## Gaps vs Phase 5d.1 requirements

| Area | Current state | Gap |
|---|---|---|
| Benchmarks | Single-sample cells | Need ≥5 text / ≥5–10 structured repeats |
| Structured validation | JSON parse only | Need Pydantic/schema authority; reject empty/fabricated fills |
| Cancel | Cooperative between attempts | In-flight HTTP not aborted; Ollama may continue |
| Retry budget | Per-attempt timeout × retries | Need overall deadline so retries cannot unbounded-extend |
| HTTP 5xx / 429 | Partial via string match | Need status-code classification |
| Capability profiles | Docs only | Need code-level profile records |
| Tool-calling | 1 live probe + TestModel | Need repeated Broker-mediated runs |
| Connection cleanup | New Client per call | Need cancel closes client; no abandoned tasks |

## Non-goals

No OpenRouter, LiteLLM, architecture redesign, L2/L3, commits.
