# 04 — Target Architecture (Freeze-Aligned)

**Authority:** [`../PYRA_ARCHITECTURE_BASELINE.md`](../PYRA_ARCHITECTURE_BASELINE.md)

---

## Diagram

```text
┌──────────────────────────────────────────────────────────────┐
│ USER → Mark-LIII → Dot → PYRA MASTER                         │
│                         │                                    │
│            ┌────────────┼────────────┐                       │
│            ▼            ▼            ▼                       │
│      Project OS   ModelGateway   Agent Runtime               │
│      (authority)  (Ollama/cloud)       │                     │
│                                       ▼                      │
│                              PydanticAI specialists          │
│                                       │                      │
│                                       ▼                      │
│                              BrokerClient  ◄── INTERNAL PATH  │
│                                       │                      │
│                                       ▼                      │
│                              Device Broker                   │
│                         policy · approve · audit             │
│                                       │                      │
│                          approved tools / hardware           │
└──────────────────────────────────────────────────────────────┘

Side paths (not on every call):
  External MCP client → MCP adapter → Device Broker (same policy)
  Engineering OS (+ optional LangGraph) → BrokerClient → Device Broker
  n8n = Automation OS (separate)
```

---

## Ownership table

See Baseline §11.4 — Master coordinates; Runtime runs specialists; PydanticAI implements them; LangGraph optional for durable Eng flows; Broker authorizes; Project OS stores truth.

---

## Tool invocation (normative)

**Internal:** Agent → BrokerClient → Device Broker → result → agent → Master.  
**External:** MCP → adapter → Device Broker.  
**Never:** Agent → raw shell/serial/flash.

---

## Approvals

Sensitive ops use operation-bound one-time tokens validated by Device Broker (ADR-004).

---

## Data ownership

| Data | Owner |
|---|---|
| Projects/tasks/memory/checkpoints | Project OS |
| Broker audit / approvals | Device Broker |
| Eng reports/evidence | Project artifacts via Eng OS + Broker writes |
| LangGraph checkpoints | Workflow-scoped only — not Project OS replacement |
| Provider keys | ModelGateway / secret store |
