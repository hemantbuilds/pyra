# Document 3 — Overall System Architecture

> **Baseline note (2026-11-10):** Alternative C (Hybrid) remains selected. Corrected tool path: **BrokerClient → Device Broker** for internal agents; **MCP = external interoperability only**. See [`PYRA_ARCHITECTURE_BASELINE.md`](PYRA_ARCHITECTURE_BASELINE.md). Where this document says “MCP everywhere,” treat that wording as **superseded**.

---

## 1. Requirements summary

### Functional
- Wake via Mark (voice/text/dashboard) → Master understands → project create/switch/resume  
- Multi-project continuity (context, decisions, repos, agent sessions, tasks)  
- Specialist team for research, systems, hardware, firmware, software, test, lab, docs, ops  
- Controlled Linux device access with verified outcomes  
- End-to-end embedded lifecycle with hardware evidence  
- n8n for deterministic personal automation  
- Local Master default; cloud for heavy reasoning  

### Non-functional
- Pi 8 GB feasible; migratable to stronger Linux host  
- Least privilege; no prompt-as-security  
- Modular replaceable subsystems  
- Mark loosely coupled  
- Cloud optional for basic ops  

---

## 2. Three alternatives

### Alternative A — Primarily custom PYRA

Build Master, orchestrator, Project OS, Device Broker, agent runners, browser stack in-house. Use only Ollama HTTP + raw subprocess tools. Minimal reuse of OpenClaw/OpenHands/n8n MCP.

| Dimension | Score (1–5) | Note |
|---|---|---|
| Complexity | 2 | Large build surface |
| Dev time | 2 | Slowest to capability |
| Resource use | 4 | Lean if disciplined |
| Reliability | 3 | Depends entirely on us |
| Extensibility | 4 | Full control |
| Security | 4 | Can design broker correctly |
| Project persistence | 5 | Custom fit |
| Multi-agent | 3 | Must invent patterns |
| Embedded support | 5 | Custom fit |
| Maintainability | 3 | All bugs are ours |
| Vendor independence | 5 | High |

### Alternative B — OpenClaw-based + custom embedded

OpenClaw Gateway as core; Mark becomes a channel/client; n8n via OpenClaw MCP; embed engineering as plugins; Project OS bolted on.

| Dimension | Score | Note |
|---|---|---|
| Complexity | 3 | Learn OpenClaw deeply |
| Dev time | 3 | Faster chat/agent basics |
| Resource use | 2 | Gateway+Mark+Ollama+n8n on 8 GB risky |
| Reliability | 4 | Mature gateway |
| Extensibility | 4 | Plugins/MCP |
| Security | 3 | Powerful defaults need hardening |
| Project persistence | 2 | Not an embedded Project OS |
| Multi-agent | 4 | Native routing |
| Embedded support | 2 | Mostly custom anyway |
| Maintainability | 3 | Upstream coupling |
| Vendor independence | 3 | MIT but architectural lock-in |

### Alternative C — Hybrid (SELECTED)

Custom Master + Project OS + Device Broker; **BrokerClient for internal tools**; MCP for **external** interoperability; ACP deferred for coding sessions; n8n for personal automation; Mark plugin face; PydanticAI specialists; **selective** LangGraph for durable engineering graphs only.

| Dimension | Score | Note |
|---|---|---|
| Complexity | 4 | Moderate, bounded modules |
| Dev time | 4 | Reuse protocols + Mark |
| Resource use | 4 | Start services on demand |
| Reliability | 4 | Verified outcomes + SQLite truth |
| Extensibility | 5 | Standard agent interface |
| Security | 5 | Broker levels independent of LLM |
| Project persistence | 5 | First-class Project OS |
| Multi-agent | 4 | Master-mediated + task queue |
| Embedded support | 5 | Dedicated Engineering OS |
| Maintainability | 4 | Clear boundaries |
| Vendor independence | 5 | Swappable models/agents |

**Selection: C.** Justification: matches mandatory rules (loose Mark coupling, MCP≠orchestrator, ACP≠universal bus, n8n≠brain); maximizes reuse of *protocols* without inheriting a second personal-assistant product; keeps Pi resource budget controllable; centers Project OS and embedded evidence — which neither OpenClaw nor Mark provide.

---

## 3. Recommended system diagram

```
                    ┌──────────────────────┐
                    │  Operators           │
                    │  Voice / Text / Phone │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │  Mark-LIII Face      │
                    │  wake, HUD, confirm  │
                    │  plugin → Master API │
                    └──────────┬───────────┘
                               │ HTTP/SSE (localhost)
                    ┌──────────▼───────────┐
                    │  PYRA MASTER SERVICE │
                    │  Intent · Router     │
                    │  Orchestrator        │
                    │  Approvals bridge    │
                    └──────────┬───────────┘
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
 ┌────────────────┐  ┌─────────────────┐  ┌──────────────────┐
 │ PROJECT OS     │  │ AGENT RUNTIME   │  │ DEVICE BROKER    │
 │ registry       │  │ specialist      │  │ MCP servers      │
 │ tasks          │  │ runners         │  │ Level 0–3        │
 │ memory         │  │ session store   │  │ outcome contract │
 │ checkpoints    │  │ cloud / local   │  │ audit log        │
 │ artifacts      │  │ ACP adapters    │  └────────┬─────────┘
 └────────┬───────┘  └────────┬────────┘           │
          │                   │                    │
          │                   ▼                    ▼
          │          ┌─────────────────┐  ┌──────────────────┐
          │          │ Model Gateway   │  │ Host resources   │
          │          │ Ollama + Cloud  │  │ fs/shell/browser │
          │          │ fallback ladder │  │ serial/flash/... │
          │          └─────────────────┘  └──────────────────┘
          │
          ▼
 ┌────────────────┐
 │ AUTOMATION     │
 │ n8n (MCP/WH)   │
 └────────────────┘
```

---

## 4. Subsystem ownership

| Subsystem | Process | Language | Data |
|---|---|---|---|
| Mark Face | existing Mark | Python/Qt | Mark memory/config |
| Master | `pyra-master.service` | Python 3.13 | none authoritative |
| Project OS | library in Master (+ CLI) | Python | `~/PyraWork` + SQLite |
| Agent Runtime | workers under Master | Python | session JSON per project |
| Device Broker | `pyra-device.service` or Master-embedded MCP | Python | policy DB + audit log |
| Model Gateway | part of Master | Python | provider config |
| n8n | Docker when ready | Node (upstream) | Postgres volume |
| Hailo | on-demand tool | CLI/SDK | HEFs |

---

## 5. Interface map

| From → To | Protocol | Auth |
|---|---|---|
| Mark → Master | HTTP REST + optional SSE | shared localhost token |
| Master → Device Broker | MCP (stdio or HTTP) | broker token + agent identity |
| Master → Specialists | internal API / subprocess | scoped tool ACL |
| Specialist → tools | MCP via Broker only | level-limited |
| Master → n8n | MCP / webhook | n8n credential |
| Master → ACP agent | ACP stdio/JSON-RPC | OS user + project workspace bind |
| Master → Ollama | HTTP localhost | none (loopback) |
| Master → Cloud | HTTPS | API keys in secret store |

---

## 6. What is existing vs external vs custom vs experimental

| Capability | Classification |
|---|---|
| Voice wake/HUD | Existing (Mark) |
| Outcome/confirm/undo patterns | Existing (reuse concepts) |
| Ollama chat+tools | Existing (pukky/Ollama) |
| MCP/ACP/n8n | External projects |
| Project OS | **Custom** |
| Device Broker + levels | **Custom** |
| Master orchestrator | **Custom** (pukky-inspired) |
| Embedded bring-up evidence | **Custom** workflows |
| Hailo LLM | **Experimental** — out of critical path |
| Wayland full desktop puppetry | **Unverified / likely unavailable** |
| OpenHands always-on | **Deferred** |

---

## 7. Evolution path to stronger hardware

Same services; raise concurrency limits; allow Docker sandboxes for coding agents; optionally run n8n/Postgres off-box; Master remains API-compatible. No architecture rewrite.
