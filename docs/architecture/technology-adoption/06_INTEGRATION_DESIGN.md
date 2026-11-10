# 06 — Integration Design (Freeze-Aligned)

**Authority:** Baseline v1.0 · ADR-001 / ADR-003

---

## 1. Internal tool path (mandatory for agents)

```text
PydanticAI specialist
  → BrokerClient
  → Device Broker (policy, approval, audit)
  → tool execution
  → structured result
```

No MCP hop required. Failure = structured denial/error; no alternate unchecked path.

---

## 2. External MCP path (optional interoperability)

```text
External MCP client
  → MCP adapter (custom today; official SDK if PoC-1 passes)
  → Device Broker (same policy)
```

Also: PYRA may act as MCP **client** to external servers **only** through controlled adapters that still subject side effects to Broker where host/hardware is touched.

**Do not** expose unauthenticated LAN MCP.

Keep custom MCP until PoC passes. SDK migration is **not** a gate for Agent Runtime.

---

## 3. PydanticAI ↔ Runtime

Master → `runtime.run` → PydanticAI → BrokerClient tools only.

---

## 4. LangGraph ↔ Engineering OS (selective)

Eng OS may run a LangGraph for durable bring-up. Nodes invoke Runtime specialists and/or BrokerClient. Graph checkpoints are workflow-scoped. Project OS remains project truth. Graph interrupts map to operation-bound approvals.

---

## 5. ModelGateway

Stable PYRA API for completions/embeddings routing. Backends: direct Ollama, direct cloud, and **conditionally** LiteLLM SDK (ADR-003). No proxy service on Pi. Keys never passed to specialists.

---

## 6. n8n / Playwright / Docling

Unchanged intent: n8n separate Automation OS; Playwright via Broker when adopted; Docling deferred — all behind approved interfaces.
