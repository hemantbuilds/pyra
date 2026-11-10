# 10 — Updated Implementation Roadmap (Frozen Sequence)

**Authority:** [`../PYRA_ARCHITECTURE_BASELINE.md`](../PYRA_ARCHITECTURE_BASELINE.md)  
**Historical:** `../12_IMPLEMENTATION_ROADMAP.md` — sequencing superseded for technology-aware plan.

---

## Completed

| Phase | Work | Status |
|---|---|---|
| 0–4 | Audit, Master/Dot, Project OS, Device Broker, **Engineering OS discovery** | **Completed** |

---

## Planned sequence

| Phase | Work | Main objective |
|---|---|---|
| **5a** | MCP SDK PoC | Validate official SDK for **external** MCP ↔ Broker; keep custom until pass |
| **5b** | Agent Runtime foundation | PYRA Runtime + **BrokerClient**; Master delegation |
| **5c** | PydanticAI specialists | Small roster (`lab`/`research`/`firmware`) |
| **5d** | ModelGateway evaluation | Direct providers vs **conditional** LiteLLM SDK |
| **6** | Engineering OS L2 | Controlled **build** + **serial** (operation-specific perms); evidence |
| **7** | Engineering OS L3 | Operation-bound approval + flash/erase + **runtime verify** |
| **8** | Durable eng workflows | **Selective LangGraph** when needed |
| **9** | Additional capabilities | Playwright; expanded n8n |
| **10** | Observability & docs | OTEL; deferred UI/Docling |
| **11** | External agent interop | Evaluate A2A / ACP |

---

## Sequencing rules (normative)

1. **5a must not block 5b** if MCP SDK compatibility is problematic.  
2. Internal agents use **BrokerClient** regardless of MCP SDK adoption.  
3. **ModelGateway** abstraction exists before any provider library is mandatory.  
4. Do not implement LangGraph before a real durable workflow requires it.  
5. Do not implement all specialists at once.  
6. Do not begin L3 flashing before operation-bound approval is implemented and validated.  
7. Do not expose unrestricted hardware access to agents.  
8. Do not pull deferred technologies into early phases “to complete the roadmap.”  
9. Build success ≠ flash success ≠ runtime verification.

---

## Critical path

```text
5b Agent Runtime + BrokerClient
  → 5c PydanticAI specialists
  → 5d ModelGateway eval
  → 6 L2 build/serial
  → 7 L3 approved flash + verify
  → 8 LangGraph if needed

Parallel: 5a MCP SDK PoC (external only)
```
