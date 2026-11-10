# Architecture Decision Records — Freeze Corrections (2026-11-10)

**Status of all five:** **ACCEPTED** (architecture decisions).  
Implementation/PoC validation is **not** claimed complete.

Authoritative baseline: [`../PYRA_ARCHITECTURE_BASELINE.md`](../PYRA_ARCHITECTURE_BASELINE.md)

---

## ADR-001 — Internal BrokerClient vs MCP Transport

- **Status:** ACCEPTED  
- **Context:** Technology adoption risked making official MCP the mandatory hop for every agent tool call. MCP is an interoperability protocol, not PYRA’s internal security bus.  
- **Decision:** Internal specialist tool execution is `Agent → BrokerClient → Device Broker → execute/audit`. MCP (custom today; official SDK if PoC passes) is for **external** MCP clients/servers exposing the **same** Broker policy. MCP SDK migration is **not** a prerequisite for Agent Runtime.  
- **Alternatives:** MCP-everywhere internal bus; agents call host tools directly; dual policy engines.  
- **Consequences:** BrokerClient is a first-class contract; MCP adapter is optional/side path.  
- **Security:** Device Broker remains sole authorization authority; MCP must not implement alternate permissions.  
- **Implementation:** Keep custom MCP until PoC; build Agent Runtime on BrokerClient.  
- **Validation:** PoC-1 for SDK; security tests that internal path never requires MCP.

---

## ADR-002 — PydanticAI and LangGraph Separation

- **Status:** ACCEPTED  
- **Context:** Avoid treating PydanticAI and LangGraph as interchangeable orchestrators.  
- **Decision:** **PydanticAI** implements specialists under Agent Runtime. **LangGraph** is selective for durable multi-step engineering workflows (checkpoint/HITL/retry). **Master** remains overall coordinator. **Project OS** remains authoritative state. LangGraph must not sit between every agent and Broker, replace Master, or become a second Project OS.  
- **Alternatives:** LangGraph-only; PydanticAI-only for all pipelines; CrewAI.  
- **Consequences:** Clear roster vs workflow ownership; LangGraph deferred until Phase 8 need.  
- **Security:** Workflow nodes still call BrokerClient; interrupts map to Broker-validated approvals.  
- **Implementation:** Phase 5b/5c agents first; LangGraph only when durable Eng OS workflow exists.  
- **Validation:** Agent Runtime works without LangGraph; later PoC-4 for graph HITL.

---

## ADR-003 — Conditional LiteLLM Adoption

- **Status:** ACCEPTED  
- **Context:** Avoid making LiteLLM mandatory for all model calls or deploying a Pi proxy.  
- **Decision:** Retain **ModelGateway** as PYRA-owned abstraction. Evaluate direct Ollama + ≥1 cloud provider vs LiteLLM SDK. Adopt LiteLLM **only if** PoC shows measurable benefit (compat, maintenance, fallback, usage, resources). **No** LiteLLM proxy on Raspberry Pi. Agents never hold provider keys.  
- **Alternatives:** Mandate LiteLLM now; forever hand-roll every provider.  
- **Consequences:** Phase 5d evaluation; ModelGateway API stays stable.  
- **Security:** Keys stay in gateway/env/keyring; not in agent context.  
- **Implementation:** Extend ModelGateway interface first; library choice behind it.  
- **Validation:** Side-by-side PoC metrics before ADOPT.

---

## ADR-004 — Operation-Bound Human Approval

- **Status:** ACCEPTED  
- **Context:** Generic “user approved” claims are insufficient for flash/erase and other sensitive ops.  
- **Decision:** Sensitive operations require **exact-operation** approval records and a **server-generated, one-time, expiring** token validated **only by Device Broker**. Binding includes project/task, device identity/interface, operation type, artifact path + hash (when applicable), parameters, level, expiry. Any material change invalidates approval. Agents cannot mint or self-authorize tokens or raise their own max_level.  
- **Alternatives:** Session-wide L3 grant; trust agent boolean; Master-only check without Broker revalidation.  
- **Consequences:** Approval object design before L3 flash (Phase 7). Audit lifecycle includes WAITING_FOR_APPROVAL / EXPIRED.  
- **Security:** Critical invariant — no model/agent/MCP client bypasses Broker or independently authorizes hardware ops.  
- **Implementation:** Extend Broker audit statuses; Mark confirm returns token reference.  
- **Validation:** Tamper tests (hash change, reuse, expiry) must deny.

---

## ADR-005 — Serial Operation Permission Separation

- **Status:** ACCEPTED  
- **Context:** Treating all serial access as one permission conflates observation with command and persistence.  
- **Decision:** Classify separately: enumeration/metadata (L0); open connection (controlled); passive capture (L0/L1 bounded); UART TX / commands (L2+ by impact); persistent settings (L3 where applicable); flash/erase (L3 + ADR-004). Engineering OS owns workflow/evidence; Device Broker owns enforcement.  
- **Alternatives:** Single “serial” L1 tool; all serial as L3.  
- **Consequences:** Future Broker tools must declare class; Eng OS Phase 6/7 sequenced accordingly.  
- **Security:** Receive ≠ transmit ≠ flash.  
- **Implementation:** New tools/policy entries per class — not one mega-tool.  
- **Validation:** Policy tests per class; no TX via capture tool.
