# 05 — Agent Runtime Design (Freeze-Aligned)

**Authority:** [`../PYRA_ARCHITECTURE_BASELINE.md`](../PYRA_ARCHITECTURE_BASELINE.md) · ADRs 001–002

---

## Goals

- PYRA-owned Runtime; specialists via **PydanticAI**.  
- Tools **only** via **BrokerClient** (not mandatory MCP).  
- Project OS remains memory authority.  
- Small on-demand roster.

---

## Responsibilities

| Layer | Does |
|---|---|
| Master | Intent, project context, delegate, approvals UX, respond |
| Agent Runtime | Register/select agents, bound context, lifecycle, validate structured results |
| PydanticAI | Implement specialists |
| LangGraph | Optional durable Eng OS pipelines calling specialists as nodes |
| BrokerClient | Internal controlled tool API |
| Device Broker | Authorize / execute / audit |

---

## Interface (conceptual)

**Registration:** manifest id, version, description, I/O schemas, model route, tool allowlist, max_level, timeouts, retries, memory scopes.

**Run:** `runtime.run(agent_id, AgentRunRequest) → AgentRunResult`

**AgentRunRequest:** `project_id`, `task_id?`, `goal`, `artifacts[]`, `parent_run_id?`

**AgentRunResult:**  
`agent_id`, `task_id`, `project_id`, `status` (`done|failed|blocked|needs_approval`), `summary`, `result`, `evidence`, `warnings`, `errors`, `recommended_next_action`

Hardware discovery results must separate **observed facts** vs **inferred** identity/confidence — never invent devices.

---

## Tool access

```text
Specialist tool stub → BrokerClient.call(tool, args, principal, max_level, project_id)
                    → Device Broker.invoke
```

Manifest `tool_allowlist` ∩ Broker registry. MCP is not required on this path.

---

## Initial roster (5c — not all at once)

| Agent | Role |
|---|---|
| `lab` / hardware discovery assist | Discovery interpretation (Broker L0 tools) |
| `research` | Docs/web with citations |
| `firmware` | Firmware assist (L1 workspace; L2 build later) |

Later: architecture, build/toolchain, verification, documentation, desktop, ops.

---

## Context isolation

Runtime passes **bounded** Project OS context for the task. Agent chat history is not authoritative. State mutations go through Master/Project OS APIs — agents do not own the DB.

---

## Failure / approval

Provider failures → retry then `blocked`. Tool denials → surface Broker errors. L2/L3 → `needs_approval` → operation-bound token (ADR-004) → Broker re-check.
