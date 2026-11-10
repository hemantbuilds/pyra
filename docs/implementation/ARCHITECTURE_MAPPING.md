# Architecture Mapping — Phase 0 Audit

**Date:** 2026-11-10  
**Repo:** `/home/hem/pyra`  
**Basis:** Docs in `docs/architecture/` + live tree inspection  

> **Architecture Baseline v1.0 (FROZEN):** [`../architecture/PYRA_ARCHITECTURE_BASELINE.md`](../architecture/PYRA_ARCHITECTURE_BASELINE.md) — consult before Phase 5+ implementation.

---

## 1. Existing components

| Component | Location | Status | Reuse |
|---|---|---|---|
| Mark-LIII face | `Mark-LIII/` | Working voice/HUD/tools | Keep untouched as face |
| Plugin loader | `Mark-LIII/core/plugin_loader.py` | Solid | Drop-in plugin for Dot |
| Outcome contract | `Mark-LIII/core/outcome.py` | Solid | Copy vocabulary into Master/Broker |
| Confirm gate | `Mark-LIII/core/confirm.py` | Solid | Bridge later for Level 3 |
| pukkyAI loop | `/home/hem/pukkyAI/pukky.py` | Prototype | Evolve into `model_gateway` + tool loop |
| Ollama | localhost:11434 | Active; `qwen2.5:3b`, `gemma3:1b` | Master default LLM |
| Architecture docs | `docs/architecture/` | Complete | Source of truth |
| Hailo-8 | `/dev/hailo0` | Present | Later lab tools |

## 2. Planned vs missing

| Planned subsystem | Present? | Notes |
|---|---|---|
| Dot routing layer | **No** | Spec introduces Dot; older docs had Mark→Master direct. **Implement Dot as new thin router.** |
| PYRA Master API | **No** | Phase 1 |
| Project OS | **Yes (Phase 2)** | `agent-os/project_os/` + `~/PyraWork`; see `PROJECT_OS.md` |
| Device Broker / MCP | **Yes (Phase 3)** | `agent-os/device_broker/`; see `DEVICE_BROKER.md` |
| Engineering OS | **Yes (Phase 4 discovery)** | `agent-os/engineering_os/`; flash/bring-up later |
| Agent Runtime | **No** | Phase 8 (defer heavy roster) |
| n8n Automation OS | **No** | Phase 9; not on bring-up critical path |
| `~/PyraWork` | **Yes (Phase 2)** | Created on first Project OS use; `PYRA_WORK_ROOT` override |
| `agent-os/` tree | **Yes** | Master + Dot + Project OS |

## 3. Architectural conflict: Dot

| Source | Flow |
|---|---|
| Doc 3 / Doc 4 (2026-11-09) | Mark plugin → Master HTTP |
| This development mission | Mark → **Dot** → Master |

**Resolution:** Implement **Dot** as a first-class thin command-routing module. Mark talks only to Dot. Dot validates/forwards to Master. Phase 1 hosts Dot and Master in one process (Pi RAM) with separate URL prefixes so they can split later.

## 4. Reusable patterns from pukky

- Ollama `/api/chat` client  
- Structured tool-call loop (later for Broker)  
- Destructive-command blocklist mindset → Broker policy  
- Hailo as vision tool only  

## 5. Required modifications (Mark)

- **Only** add `Mark-LIII/plugins/pyra_dot.py` (or symlink from `agent-os/integrations/mark_plugin/`).  
- Do **not** fork `main.py` / Live loop.

## 6. Integration dependencies

```
Phase1 Master+Dot  →  Phase2 Project OS  →  Phase3 Device Broker
        → Phase4 Engineering OS  →  Phase5–7 Bring-up vertical
```

## 7. Implementation order (locked)

0. Mapping (this doc)  
1. Master + Dot + Mark plugin + tests  
2. Project OS  
3. Device Broker (usb/serial/fs/shell)  
4–7. Engineering bring-up capability  
8+. Agents / n8n / hardening  

## 8. Host notes (re-checked 2026-11-10)

- Ollama reachable with full host access; models present.  
- System FastAPI **not** installed → `agent-os` gets its own venv.  
- Wayland/labwc still limits desktop puppetry (unchanged).  
- No serial devices attached at audit time.
