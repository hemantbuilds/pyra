# 08 — Deployment & Resource Plan (Raspberry Pi 5)

**Verified host:** aarch64, ~8 GB RAM, Debian-class, Python 3.13, Ollama + Mark already competing for RAM.

---

## 1. Classification

| Dependency | Class | Notes |
|---|---|---|
| Mark-LIII | Must local | Face |
| Master+Dot+Broker+Project OS | Must local | Core |
| Ollama + small models | Must local (or degraded) | Already present |
| PydanticAI agents | On-demand local | No always-on |
| MCP SDK | In-process / stdio | Light |
| LiteLLM SDK | In-process | Prefer over proxy |
| LiteLLM Proxy | Optional remote/side | Avoid always-on on Pi |
| Playwright + browser | On-demand | Large disk/RAM spike |
| PlatformIO/Zephyr toolchains | Local disk-heavy | Install per need |
| n8n | Can remote / start-stop | Docker RAM |
| Phoenix/Langfuse | Optional / remote | ELv2/license + RAM |
| Renode | Optional CI host | Heavy |
| Cloud LLMs | Cloud-only API | Keys local |
| Hailo | Optional local | Vision only |

---

## 2. Rough RAM budget (order-of-magnitude, not measured)

| Process | Order |
|---|---|
| OS + desktop | 1–2 GB |
| Mark | 0.5–1.5 GB (unverified exact) |
| Ollama + 3B model | 2–4 GB |
| Master | <300 MB typical |
| Playwright job | +0.5–1.5 GB spike |
| n8n Docker | +0.5–1+ GB |

**Implication:** Do not co-run Mark + large Ollama + n8n + tracer + Playwright permanently. Serialize heavy jobs; prefer cloud for heavy reasoning when online.

---

## 3. Disk

Toolchains (ARM GCC, ESP-IDF, Zephyr) can consume many GB. Keep under project or user tool dirs; document installs; never auto-apt upgrade from agents.

---

## 4. Services

**systemd user units (proposed later):** `pyra-master.service` only by default.  
Optional: `ollama`, `n8n`, tracer — separate units, disabled by default.

---

## 5. Hailo

Use only for vision HEFs. **Do not** plan general LLM inference on Hailo without a verified stack (prior ADR).
