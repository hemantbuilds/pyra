# 12 — Risk Register (Freeze-Aligned)

| ID | Risk | L | I | Mitigation |
|---|---|---|---|---|
| R1 | Framework lock-in | M | M | Runtime adapter; BrokerClient contract |
| R2 | MCP SDK dep clash | M | H | PoC-1; 5a non-blocking for 5b |
| R3 | Pi RAM exhaustion | H | H | Always-on vs on-demand split; measure |
| R4 | MCP/agent bypass of Broker | M | H | ADR-001; security tests; freeze invariant |
| R5 | LangGraph as second Project OS | M | H | ADR-002; workflow-scoped checkpoints only |
| R6 | LiteLLM adopted without value | M | M | ADR-003 CONDITIONAL + PoC-3 |
| R7 | Generic approval reused for flash | M | H | ADR-004 operation-bound tokens |
| R8 | Serial TX via “capture” tool | M | H | ADR-005 class separation |
| R9 | Hardware mis-ID → wrong flash | M | H | Evidence/confidence; L3 approval |
| R10 | Phoenix ELv2 / tracer RAM | M | M | Defer UI tracers |
| R11 | Cloud outage | M | M | Ollama fallback via ModelGateway |
| R12 | Secret leakage | M | H | Redaction; no keys in agent context |
| R13 | Overbuilding unused agents | H | M | Small roster |

**Top watch:** R3, R4, R7, R2
