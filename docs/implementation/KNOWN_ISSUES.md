# Known Issues

| ID | Issue | Severity | Status |
|---|---|---|---|
| K1 | Dot not in original architecture docs | Doc conflict | Resolved |
| K2 | System Python lacks FastAPI | Build | Use `agent-os/.venv` |
| K3 | Mark `.venv` pip broken | Host | Mark plugin uses stdlib `urllib` |
| K4 | Ollama may be unreachable from sandboxed tools | Dev | Use host network / `all` for live |
| K5 | Serial hardware may be absent | Lab | Discovery reports none / unknown honestly |
| K7 | Checkpoint restore does not rewind workspace files | Phase 2 | By design |
| K8 | SQLite shared across FastAPI threads | Runtime | `check_same_thread=False` + locks |
| K11 | MCP is minimal stdio JSON-RPC subset | Phase 3 | Sufficient for tools/list+call |
| K12 | Browser/desktop backends not implemented | Scope | Deferred |
| K13 | Device node listing was path-only | Phase 3 | Superseded by Phase 4 enumerate_* tools |
| K14 | Write roots were workspace+global only | Phase 3 | Extended with artifacts/reports |
| K15 | Onboard `/dev/ttyAMA*` appear as serial with no USB IDs | Expected | Marked unknown — not assumed MCU |
| K16 | USB VID/PID can identify bridge/probe more than target MCU | Limit | Confidence capped; unresolved notes |
| K17 | Full bring-up / flash not implemented | Scope | Phase 5+ |
| K18 | SDK path detection (ESP-IDF/Cube) is unknown | Phase 4 | Assessment reports unknown SDK |
