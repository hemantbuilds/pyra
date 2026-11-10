# 07 — Security & Permission Integration (Freeze-Aligned)

**Authority:** Baseline §11.6 · ADR-004 · ADR-005  
**Invariant:** No model, agent, workflow, or external MCP client can bypass Device Broker or independently authorize sensitive hardware operations.

---

## Permission levels

| Level | Scope |
|---|---|
| L0 | Read-only discovery/inspection |
| L1 | Controlled workspace / approved non-destructive ops |
| L2 | Builds, controlled execution, approved serial TX (as classified) |
| L3 | Flash, erase, sensitive persistent hardware configuration |

Current code ceiling remains L1 until L2/L3 tools and approvals are implemented.

---

## Serial operation classes (ADR-005)

| Operation | Class | Notes |
|---|---|---|
| Enumerate serial devices | L0 | Read-only |
| Read VID/PID / metadata | L0 | Read-only |
| Identify interfaces | L0 | Read-only |
| Open serial connection | Controlled | Scoped device |
| Passive capture | L0/L1 | Bounded duration/output |
| Send UART / commands | L2+ | Impact-based |
| Persistent device settings | L3 | Where applicable |
| Flash / erase | L3 | Operation-bound approval |

Receive ≠ transmit ≠ flash.

---

## Operation-bound approval (ADR-004)

Binding fields (minimum): project_id, request/task id, device identity, interface, operation type, artifact path + cryptographic hash (when applicable), parameters, permission level, expiry, one-time approval id.

**Token:** server-generated, single-use, expiring; validated **only** by Device Broker; audited; never agent-minted.

Lifecycle:  
`REQUESTED → VALIDATED → WAITING_FOR_APPROVAL → APPROVED → EXECUTING → COMPLETED|FAILED|DENIED|EXPIRED`

Do not log raw token secrets.

---

## Framework rules

| Component | Rule |
|---|---|
| PydanticAI | BrokerClient tools only |
| LangGraph | BrokerClient; HITL → Broker tokens |
| MCP adapter | Same Broker policy; no alternate ACL |
| ModelGateway / LiteLLM | No tool rights; no key leakage |
| n8n | Curated; send/push gated |

---

## Audit

Preserve Broker audit for all ops; extend statuses for approval wait/expire. Redact secrets.
