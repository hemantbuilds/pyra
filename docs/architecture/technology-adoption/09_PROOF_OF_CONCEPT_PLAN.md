# 09 — Proof-of-Concept Plan (Freeze-Aligned)

PoCs validate **conditional** tech. None are claimed passed in Architecture Baseline v1.0.

---

## PoC-1 — Official MCP SDK as **external** adapter

| | |
|---|---|
| Demonstrate | SDK server/client → Device Broker; jail/allowlist intact; stdio (+ HTTP if feasible) |
| Why | EVALUATE decision for external interoperability |
| **Not** | Required for internal Agent Runtime |
| Success | Security tests pass; deps OK on Py 3.13 / aarch64 |
| Failure | Dep conflict or policy bypass |

## PoC-2 — PydanticAI + BrokerClient

| | |
|---|---|
| Demonstrate | Specialist with allowlisted BrokerClient tools; structured AgentRunResult |
| Why | Unblocks Phase 5b/5c |
| Success | No host bypass; Project OS artifact optional |
| Failure | Needs unrestricted shell |

## PoC-3 — ModelGateway: direct vs LiteLLM SDK

| | |
|---|---|
| Demonstrate | Same Gateway API → Ollama + one cloud; compare complexity/latency/deps/fallback |
| Why | LiteLLM remains **CONDITIONAL** |
| Success | Measurable benefit **or** decide retain direct only |
| Failure | Adopt LiteLLM without evidence |

## PoC-4 — LangGraph durable skeleton (after real need)

| | |
|---|---|
| Demonstrate | discover→build→interrupt approve→deny flash without token |
| Why | LangGraph CONDITIONAL |
| Success | Interrupt ↔ operation-bound approval model |
| Failure | Graph becomes second Project OS |

## PoC-5 — Observability (later)

OTEL spans first; UI tracer deferred.
