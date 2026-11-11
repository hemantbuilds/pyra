# Agent Runtime — Phase 5b Implementation

**Status:** Phase 5b foundation + Phase 5c PydanticAI Research Agent  
**Architecture:** PYRA Baseline v1.0  
**Date:** 2026-11-10 (5c update)  

---

## What was implemented

| Item | Status |
|---|---|
| `agent-os/agent_runtime/` package | Implemented |
| Agent registry (register / get / list / capabilities) | Implemented + unit-tested |
| `AgentTask` / `AgentResult` / `ExecutionStatus` contracts | Implemented + unit-tested |
| Execution lifecycle | Implemented + unit-tested |
| Bounded `ExecutionContext` | Implemented + unit-tested |
| `AgentBrokerSession` → existing `device_broker.client.BrokerClient` | Implemented + unit-tested |
| Master capability `agent_runtime` (`AGENT_LIST` / `AGENT_RUN`) | Implemented + integration-tested |
| Deterministic Dot/Master phrases | Implemented |
| HTTP `GET /v1/agents`, `POST /v1/agents/run` | Implemented (Master/CLI; not Mark-facing) |
| Built-in `echo` + `broker_probe` agents | Deterministic test doubles |
| PydanticAI adapter + `research` agent | Phase 5c — see `PHASE5C_IMPLEMENTATION.md` |
| `ResearchReport` structured output | Phase 5c |
| ModelGateway provider resolution | Phase 5c (Ollama / test / optional OpenAI) |

## What was not implemented (later phases)

| Item | Phase |
|---|---|
| Additional PydanticAI specialists | later |
| MCP SDK migration | 5a (non-blocking) |
| LiteLLM / ModelGateway expansion | 5d |
| LangGraph durable workflows | 8 |
| L2/L3, flash, serial TX, operation-bound approval | 6–7 |

---

## Runtime architecture

```text
Mark → Dot → Master
               │
               ├─ Project OS (bounded context only)
               └─ Agent Runtime.run(AgentTask)
                      │
                      ├─ Registry.resolve(agent_id|capability)
                      ├─ ExecutionContext (frozen project_id)
                      ├─ SpecialistAgent.run(...)
                      │      └─ AgentBrokerSession.call(tool, args)
                      │             └─ BrokerClient → Device Broker
                      └─ validate AgentResult → Master
```

**Internal tools:** BrokerClient only (no MCP hop).  
**Security authority:** Device Broker.  
**Project truth:** Project OS (Runtime does not add a database).

---

## Registration & execution flow

1. `TASK_RECEIVED` → validate `AgentTask`  
2. `TASK_VALIDATED` → resolve agent  
3. `AGENT_RESOLVED` → prepare bounded context + `AgentBrokerSession`  
4. `CONTEXT_PREPARED` → `EXECUTING` (timeout enforced)  
5. `RESULT_VALIDATED` → terminal status (`COMPLETED` / `FAILED` / `BLOCKED` / …)

Failure paths: `REJECTED` (bad task), `FAILED` (unknown agent, exception, timeout, invalid result), `BLOCKED` (no broker / allowlist / Broker denial).

---

## BrokerClient integration

- Reuses `device_broker.client.BrokerClient` (same path Master already uses).  
- `AgentBrokerSession` adds: tool allowlist, capped `max_level` (Phase ceiling **L1**), forced `project_id`, call timeout, principal `agent:<id>`, evidence of `operation_id`s.  
- Demonstrated: `get_system_info` (L0) success; allowlist denial; Broker permission denial (L1 tool with L0 max).

---

## Master integration

| Phrase | Intent |
|---|---|
| `list agents` | `AGENT_LIST` |
| `run echo agent` / `run broker probe agent` | `AGENT_RUN` |

Requires an **active project** for `AGENT_RUN`. Results appear in `InteractResponse.evidence.agent_result`.

---

## Validation notes

| Claim | Evidence |
|---|---|
| Unit-tested | `tests/agent_runtime/` |
| Integration-tested (Master/Dot) | same + existing master suite |
| Physical hardware | **Not validated** (not required for 5b) |
| Open validation items OV-1…OV-6 | **Unchanged** — not claimed passed |

---

## Package layout

```text
agent-os/agent_runtime/
  contracts.py      AgentTask, AgentResult, AgentManifest, ExecutionStatus
  agent.py          SpecialistAgent ABC
  registry.py       AgentRegistry
  context.py        ExecutionContext
  broker_session.py AgentBrokerSession
  runtime.py        AgentRuntime
  service.py        get/reset singleton
  bootstrap.py      echo + broker_probe
  agents/           deterministic foundation agents
```
