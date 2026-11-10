# 00 — Executive Summary (Aligned to Architecture Baseline v1.0)

**Date:** 2026-11-10 (updated for freeze corrections)  
**Authoritative baseline:** [`../PYRA_ARCHITECTURE_BASELINE.md`](../PYRA_ARCHITECTURE_BASELINE.md)  
**Code status:** Phases 0–4 complete. Eng OS = **discovery only**.

---

## Principle

**Build what makes PYRA unique. Reuse what the industry solved. Integrate through clear interfaces. Keep Device Broker as security authority.**

---

## Five freeze corrections (summary)

1. **Internal tools = BrokerClient → Device Broker.** MCP is external interoperability, not mandatory internal transport.  
2. **PydanticAI = specialists; LangGraph = selective durable workflows; Master = coordinator; Project OS = state.**  
3. **LiteLLM = CONDITIONAL** behind ModelGateway; no Pi proxy; evaluate vs direct providers.  
4. **Human approval = operation-bound, one-time Broker-validated tokens.**  
5. **Serial permissions are operation-specific** (enum ≠ capture ≠ TX ≠ flash).

---

## What PYRA builds / retains

Mark-LIII · Dot · Master · Project OS · Device Broker policy · BrokerClient · Engineering OS workflows · Agent Runtime · ModelGateway

---

## What PYRA reuses (direction)

| Tech | Decision |
|---|---|
| PydanticAI | **ADOPT** |
| LangGraph | **CONDITIONAL / SELECTIVE** |
| Official MCP SDK | **EVALUATE** (external path; keep custom until PoC) |
| LiteLLM SDK | **CONDITIONAL** |
| Ollama | **RETAIN** |
| PlatformIO / Zephyr / pyOCD / OpenOCD / … | **ADOPT AS REQUIRED** via Broker |
| Playwright | **ADOPT WHEN REQUIRED** |
| n8n | **RETAIN** (Automation OS) |
| OTEL | **ADOPT INCREMENTALLY** |
| CrewAI / OpenClaw foundation / cFS | **REJECT / EXCLUDED** |
| A2A, ACP, Renode, Labgrid, Docling, vector DBs, Phoenix/Langfuse | **DEFER** |

---

## Internal vs external tool paths

```text
Internal:  PydanticAI agent → BrokerClient → Device Broker → tools
External:  MCP client → MCP adapter → Device Broker (same policy)
```

---

## Critical path (does **not** require MCP SDK first)

1. Agent Runtime + BrokerClient (5b)  
2. Small PydanticAI roster (5c)  
3. ModelGateway evaluation / optional LiteLLM (5d)  
4. Parallel: MCP SDK PoC (5a) for external interoperability  
5. Eng OS L2 build + controlled serial (6)  
6. Operation-bound approval + L3 flash/verify (7)  
7. Selective LangGraph (8) when durable workflow needs it  

---

## Explicitly not next

MCP-everywhere · LiteLLM-mandatory · LangGraph-as-Master · auto-flash · unauthenticated LAN MCP · rewriting Project OS
