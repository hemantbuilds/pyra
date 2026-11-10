# Document 11 — Deployment Architecture

---

## 1. Target host budget (Pi 5 8 GB)

| Subsystem | Always-on? | RAM budget (approx) | Notes |
|---|---|---|---|
| OS + desktop | Yes | 0.8–1.5 GB | labwc session |
| Mark-LIII | When used | 0.5–1.5 GB | Qt + audio + optional models |
| Ollama idle | Yes | ~40 MB | Measured idle |
| Ollama + 3B loaded | On demand | ~2–3.5 GB | Keep_alive policy critical |
| Pyra Master | Yes (light) | 100–250 MB | No model weights |
| Device Broker | Yes (light) | 50–150 MB | |
| n8n + Postgres | Optional | 0.5–1.2 GB | Cap or offload |
| Hailo service | Yes | ~10 MB | Measured small |
| Cursor/dev tools | Dev only | Dominates today | Not production profile |

**Rule:** Do not keep 7B model + Mark + n8n + Cursor loaded together.

### Continuous vs on-demand

| Always | On-demand |
|---|---|
| Master API, Broker, Ollama daemon, HailoRT | Model weights, Playwright, ACP agents, n8n (if RAM tight), flash tools |

---

## 2. Process supervision

Prefer **systemd user or system units**:

- `pyra-master.service`  
- `pyra-device.service` (if split)  
- `ollama.service` (exists)  
- Mark: user-started or existing autostart  
- n8n: Docker with restart policy **after** Compose available  

Health: `/healthz` on Master; systemd `WatchdogSec` optional.

---

## 3. Docker policy

Use Docker for **n8n/Postgres** (and later OpenHands), not for Master/Broker core.  
Reason: device access (serial, Hailo) and low overhead.  
Missing Compose plugin is a Phase 0 install dependency (needs approval).

---

## 4. Logging / monitoring

- journald for services  
- Project `logs/` for agent runs  
- Phase 9: OpenTelemetry optional export  

---

## 5. Backup / recovery

Backup: `~/PyraWork/` + n8n volume + secret files.  
Exclude: Ollama model blobs (re-pull), Mark venv.  
Recovery: restore FS + DB; Master reconciles interrupted tasks.

---

## 6. Updates

- Mark: upstream pull carefully (BY-NC); keep plugin out-of-tree  
- Pyra: semver services  
- n8n: pinned image tags  

---

## 7. Migration to stronger PC

Same unit files; raise concurrency; move n8n to NAS; enable Docker coding sandboxes. API stable.
