# 02 — Technology Research

Sources: official docs/repos/PyPI (2026-11-10). Unverified items marked.

---

## 1. Agent frameworks

### PydanticAI
| | |
|---|---|
| Site | https://ai.pydantic.dev/ / https://pydantic.dev/pydantic-ai |
| Repo | https://github.com/pydantic/pydantic-ai |
| PyPI | `pydantic-ai` (e.g. 2.66.0 observed) |
| License | **MIT** |
| Python | **≥3.11** (compatible with 3.13) |
| MCP | First-class client/server support |
| Pi/ARM | Pure Python — expected OK (not separately benchmarked here) |
| Fit | Typed agents, structured I/O, tool calling, model string swap, MCP |
| Overlap | Would implement specialists; must not own Project OS |
| Verdict input | **ADOPT** as primary specialist framework |

### LangGraph
| | |
|---|---|
| Docs | https://docs.langchain.com/oss/python/langgraph/overview |
| License | **MIT** (LangGraph/LangChain OSS) |
| Strengths | Graphs, checkpointers, interrupts/HITL, durable graph steps |
| Weaknesses | Ecosystem gravity toward LangSmith; heavier mental model |
| Fit | Long bring-up pipelines with approve/resume — **not** everyday chat agents |
| Verdict input | **EVALUATE → ADOPT** for Engineering OS pipelines only |

### Google ADK
| | |
|---|---|
| Docs | https://google.github.io/adk-docs/ |
| Notes | Multi-agent + MCP + A2A oriented |
| Fit | Overlaps PydanticAI+A2A; adds Google-centric path |
| Verdict input | **DEFER** unless ADK-specific need appears |

### CrewAI
| | |
|---|---|
| Docs | https://docs.crewai.com/ |
| License | MIT (typical) |
| Fit | Role/crew DX; overlaps Master+Project OS task model; prior ADR-009 reject |
| Verdict input | **REJECT** for core |

---

## 2. Protocols

### MCP (Model Context Protocol)
| | |
|---|---|
| Spec | https://modelcontextprotocol.io/ |
| Python SDK | https://github.com/modelcontextprotocol/python-sdk · docs https://py.sdk.modelcontextprotocol.io/ |
| PyPI | `mcp` **v2.3.0** observed; MIT; Python ≥3.11 (docs); PyPI may list ≥3.10 |
| Transports | stdio, Streamable HTTP, SSE legacy |
| PYRA today | Minimal custom JSON-RPC subset |
| Constraint | SDK must wrap Broker; never grant tools raw |
| Dep risk | v2 wants newer pydantic / **httpx2** — PoC required |
| Verdict input | **EVALUATE → REPLACE** custom transport |

**MCP ≠ orchestrator.** Tools/resources/prompts only.

### A2A (Agent2Agent)
| | |
|---|---|
| Site | https://a2a-protocol.org/ |
| SDK | https://github.com/a2aproject/a2a-python · PyPI `a2a-sdk` 1.3.0 |
| License | **Apache-2.0** |
| Role | Opaque agent interoperability (cards, remote tasks) |
| vs MCP | MCP = tools; A2A = agent-to-agent |
| Verdict input | **DEFER** until remote/external agents |

### ACP
| | |
|---|---|
| Role | Coding-agent sessions (IDE↔agent) |
| Verdict input | **DEFER** until Coding Agent needs session resume |

---

## 3. Model gateway

### LiteLLM
| | |
|---|---|
| Site | https://www.litellm.ai/ · docs https://docs.litellm.ai/ |
| Repo | https://github.com/BerriAI/litellm |
| License | **MIT** (OSS gateway; enterprise extras separate) |
| Modes | Python SDK **or** always-on proxy |
| Providers | OpenAI-compatible, Gemini, Anthropic, Ollama, many more |
| ARM64 | Docker images advertise linux/arm64 (proxy); SDK is Python |
| PYRA today | Thin `ModelGateway` → Ollama `/api/chat` |
| Verdict input | **EVALUATE → ADOPT SDK** behind ModelGateway; **DEFER** always-on proxy on Pi |

---

## 4. Observability

### Arize Phoenix
| | |
|---|---|
| Site | https://phoenix.arize.com/ · https://github.com/Arize-ai/phoenix |
| License | Platform **Elastic License 2.0 (ELv2)**; `phoenix-otel` package Apache-2.0 |
| Notes | Self-host free; ARM Dockerfile variants exist |
| Risk | ELv2 is not OSI MIT/Apache — review for PYRA distribution goals |
| Verdict input | **EVALUATE** carefully |

### Langfuse
| | |
|---|---|
| Site | https://langfuse.com/ |
| Notes | Popular LLM tracing; self-host possible; verify current OSS license in PoC |
| Verdict input | **EVALUATE** as alternative to Phoenix |

### Recommendation seed
Start with **OpenTelemetry API + JSON audit/trace events** (already have Broker audit). Add one full UI tracer after Agent Runtime exists. **Do not deploy both Phoenix and Langfuse.**

---

## 5. Embedded / hardware tooling

| Tool | Role | License (typical) | Via Broker |
|---|---|---|---|
| **PlatformIO** | Multi-platform builds | Apache-2.0 (core) | L2 build cmds |
| **Zephyr + west** | RTOS build/test (Twister) | Apache-2.0 | L2 |
| **pyOCD** | CMSIS-DAP flash/debug | Apache-2.0 | L3 gated |
| **OpenOCD** | Probe/debug | GPL-2.0-or-later | L3 gated |
| **probe-rs** | Modern probe tooling | Apache-2.0 | L3 gated |
| **esptool** | ESP flash | GPL-2.0+ / Apache components — verify per install | L3 gated |
| **Renode** | Simulation | MIT | L2 sim tests |
| **pyserial** | UART I/O | BSD | L1 read / L2 write policy TBD |

All must be **invoked through Device Broker**, never by agents directly.

---

## 6. HIL / testing

| Tool | Role | License | Verdict input |
|---|---|---|---|
| **pytest** | Already used | MIT | **RETAIN** |
| **Labgrid** | Board power/serial/USB control for tests | **LGPLv2.1+** | **EVALUATE** for lab |
| **OpenHTF** | Phase/measurement manufacturing tests | Apache-2.0 | **DEFER** until production test benches |
| **Robot Framework** | Acceptance suites; Renode integration common | Apache-2.0 | **DEFER** |

Ownership: Engineering OS / Testing Agent orchestrates; pytest/Labgrid/OpenHTF execute.

---

## 7. Browser / desktop

| Tool | Notes | Verdict input |
|---|---|---|
| **Playwright** | Cross-browser; works better than X11-only on Wayland | **ADOPT** behind Broker |
| pyautogui / xdotool | Weak on labwc Wayland | **REJECT** as primary |

---

## 8. Automation

| Tool | Notes | Verdict input |
|---|---|---|
| **n8n** | Deterministic workflows; MCP/webhook | **RETAIN** Automation OS; not Master |

---

## 9. Document intelligence

| Tool | Notes | Verdict input |
|---|---|---|
| **Docling** | PDF/table extraction for datasheets | **EVALUATE** |
| **LlamaIndex** | RAG orchestration | **DEFER** |
| **Qdrant / Chroma** | Vector DB | **DEFER** until corpus justifies always-on DB |

Initial path: Docling → files under project `artifacts/datasheets/` + citation metadata; optional embeddings later.

---

## 10. Additional candidates

| Project | Problem | Verdict input |
|---|---|---|
| **OpenTelemetry** | Standard traces/metrics | **ADOPT** instrumentation early |
| **keyring** / OS secrets | Secret storage | **EVALUATE** |
| **uv** | Fast Python env/tooling | Optional DX |
| **probe-rs** | Already partially allowlisted | **ADOPT** when L3 |
| Hailo-8 | Vision only | **RETAIN** optional; not LLM |

---

## 11. Assumptions & open questions

**Assumptions:** Official docs remain accurate as of 2026-11-10; ARM64 Docker tags imply runnable images but RAM fit is unproven on this 8 GB host with Mark+Ollama.

**Open questions:** Exact Langfuse OSS license for chosen release; MCP v2 vs PYRA pydantic/httpx coexistence; whether LiteLLM SDK alone covers Gemini without proxy; Labgrid LGPL implications for packaging.
