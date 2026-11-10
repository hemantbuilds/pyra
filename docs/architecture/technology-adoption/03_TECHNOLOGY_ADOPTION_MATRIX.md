# 03 — Technology Adoption Matrix (Frozen Alignment)

**Authority:** [`../PYRA_ARCHITECTURE_BASELINE.md`](../PYRA_ARCHITECTURE_BASELINE.md)  
**Codes:** ADOPT · RETAIN · CONDITIONAL · EVALUATE · DEFER · REJECT · EXCLUDED

| Technology / Component | Decision | Responsibility / notes | Mandatory? | Validate before use | Pi impact | Phase |
|---|---|---|---|---|---|---|
| Mark-LIII | **RETAIN** | Face/voice UI | Yes (face) | — | Always-on | Done |
| Dot | **RETAIN** | Mark↔Master integration | Yes | — | In-Master | Done |
| PYRA Master | **RETAIN** | Central coordinator | Yes | — | Always-on | Done |
| Project OS | **RETAIN** | Authoritative project state | Yes | — | Always-on | Done |
| Device Broker | **RETAIN** | Security + execution authority | Yes | — | Always-on | Done |
| Engineering OS | **RETAIN** | Eng workflows + evidence (discovery done) | Yes | — | On-demand | Done+extend |
| Agent Runtime | **RETAIN/BUILD** | Specialist lifecycle abstraction | Yes (for agents) | Contracts | On-demand | 5b |
| BrokerClient | **RETAIN/BUILD** | **Internal** tool access interface | Yes (for agents) | Security tests | In-process | 5b |
| PydanticAI | **ADOPT** | Specialist agent implementation | For specialists | PoC-2 | On-demand | 5c |
| LangGraph | **CONDITIONAL** | Durable Eng workflows only | No | Real workflow need + PoC-4 | On-demand | 8 |
| Custom MCP JSON-RPC | **RETAIN** until PoC | Current external MCP subset | Interim | — | Light | Now |
| Official MCP Python SDK | **EVALUATE** | **External** MCP interoperability adapter | No | PoC-1 (deps, ARM, policy) | Light if in-process | 5a |
| ModelGateway | **RETAIN** | Provider-independent model interface | Yes | — | In-Master | Done+extend |
| Ollama | **RETAIN** | Local models | Preferred local | — | Always-on (measure) | Done |
| LiteLLM SDK | **CONDITIONAL** | Optional behind ModelGateway | No | PoC-3 measurable value | Library only | 5d |
| LiteLLM Proxy | **DEFER** | Not on Pi | No | — | High if run | — |
| PlatformIO | **ADOPT AS REQUIRED** | Embedded builds via Broker L2 | No | Board profile | Disk/CPU spike | 6 |
| Zephyr West | **ADOPT AS REQUIRED** | Zephyr build/test via Broker | No | Project uses Zephyr | Disk heavy | 6 |
| pyOCD / OpenOCD / probe-rs / esptool | **ADOPT AS REQUIRED** | Flash/debug via Broker L3 | No | Approval design | On-demand | 7 |
| Playwright | **ADOPT WHEN REQUIRED** | Browser via Broker | No | Wayland/RAM | Spike | 9 |
| n8n | **RETAIN** separately | Automation OS | No | — | Prefer side host | 9 |
| OpenTelemetry | **ADOPT INCREMENTALLY** | Instrumentation | No | — | Light | 10 |
| Langfuse / Phoenix | **DEFER** | Trace UI (Phoenix ELv2) | No | License + RAM | Heavy | 10 |
| Renode | **DEFER** | Simulation | No | — | Heavy | 11+ |
| Labgrid | **DEFER** | HIL orchestration | No | LGPL | Lab | 11+ |
| Docling | **DEFER** | Datasheet parse | No | Deps | On-demand | 10 |
| Qdrant / Chroma | **DEFER** | Vector DB | No | Corpus size | Service | Later |
| A2A | **DEFER** | External agents | No | Need remote agents | — | 11 |
| ACP | **DEFER** | Coding-agent sessions | No | Coding Agent need | — | 11 |
| CrewAI | **REJECT** | Overlapping framework | — | — | — | — |
| OpenClaw as foundation | **REJECT** | Not Alt C | — | — | — | — |
| cFS | **EXCLUDED** | Not in scope | — | — | — | — |

### Clarifications

- **MCP SDK does not replace BrokerClient** for internal agents.  
- **LiteLLM is not ADOPT until PoC proves value.**  
- **LangGraph is not the PYRA coordinator.**
