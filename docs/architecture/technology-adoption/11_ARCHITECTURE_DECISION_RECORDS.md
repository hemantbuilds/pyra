# 11 — Architecture Decision Records (Adoption Pack Index)

**Freeze corrections (ACCEPTED):**  
[`ADRS_ARCHITECTURE_CORRECTIONS.md`](ADRS_ARCHITECTURE_CORRECTIONS.md)

| ID | Title | Status |
|---|---|---|
| ADR-001 | Internal BrokerClient vs MCP Transport | ACCEPTED |
| ADR-002 | PydanticAI and LangGraph Separation | ACCEPTED |
| ADR-003 | Conditional LiteLLM Adoption | ACCEPTED |
| ADR-004 | Operation-Bound Human Approval | ACCEPTED |
| ADR-005 | Serial Operation Permission Separation | ACCEPTED |

**Baseline:** [`../PYRA_ARCHITECTURE_BASELINE.md`](../PYRA_ARCHITECTURE_BASELINE.md)

**Earlier adoption notes (T01–T09):** retained below as historical research-era records; where they conflict with ADR-001–005 / Baseline v1.0, **Baseline wins**.

---

### ADR-T01 — PydanticAI as primary specialist agent framework
- **Status:** Accepted direction (see ADR-002)  
- **Decision:** ADOPT PydanticAI behind Agent Runtime; tools via BrokerClient.

### ADR-T02 — LangGraph for durable engineering pipelines only
- **Status:** Accepted as CONDITIONAL (see ADR-002)

### ADR-T03 — Official MCP SDK (historical wording)
- **Status:** **Superseded in part by ADR-001**  
- **Correction:** SDK is for **external** interoperability evaluation; **not** mandatory internal transport; custom MCP retained until PoC; does not block Agent Runtime.

### ADR-T05 — LiteLLM (historical wording)
- **Status:** **Superseded by ADR-003** — CONDITIONAL, not pre-adopted.

### ADR-T09 — Alternative C
- **Status:** Affirmed in Baseline v1.0
