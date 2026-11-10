# Document 1 — Existing System Audit

**Scope:** Mark-LIII repository, pukkyAI, Raspberry Pi 5 host  
**Method:** Source inspection + read-only host commands (2026-11-09)  
**Constraint:** No installs, no system-changing commands  

---

## 1. Mark-LIII

### 1.1 Identity and provenance

| Fact | Value |
|---|---|
| Path | `/home/hem/pyra/Mark-LIII` |
| Git remote | `https://github.com/FatihMakes/Mark-LIII.git` |
| Local HEAD | `0101e54 Add files via upload` |
| Working tree | Dirty (many modified files vs origin) |
| README branding | Documents **Mark LVI** features |
| License | Creative Commons **BY-NC 4.0** (personal/non-commercial) |
| Scale | `main.py` ~2880 LOC; `ui.py` ~7499 LOC; ~56 Python modules under actions/core/providers |

**Finding:** Folder name “Mark-LIII” does not match the feature set documented as LVI. Treat as “Mark LVI-class assistant labeled LIII in this tree.”

### 1.2 Application lifecycle

```
setup.py / requirements → python main.py
  → Qt UI thread (ui.py / PyraUI)
  → asyncio voice session thread (main.py)
  → action_loader + plugin_loader discovery
  → Gemini Live session OR providers engine_pipeline
  → tool dispatch on worker threads
  → optional dashboard (FastAPI)
  → optional wake word thread
```

Threading contract (`AGENTS.md`): tools **must not** create Qt widgets; use `player.*` marshalled methods.

### 1.3 What is implemented (verified in tree)

| Area | Status | Evidence |
|---|---|---|
| Wake word | Implemented, opt-in | `core/wake_word.py`, model `models/hey_pyra.onnx`, config `wake_word_enabled` |
| STT/TTS | Dual path | Gemini Live native audio; local Whisper/Piper/system via `providers/` |
| LLM providers | Implemented | `providers/llm_openai.py` OpenAI-compat; Gemini Live in `main.py`; ladder in `core/gemini.py` |
| Tool discovery | Solid | `core/action_loader.py`, `core/plugin_loader.py` — `TOOL`/`PLUGIN` + `run` |
| Device tools | Broad | open_app, computer_control, computer_settings, desktop, browser_control, file_*, web_search, screen_processor, system_monitor |
| Coding agent | Single-worker | `actions/dev_agent.py` build/improve/status → `~/Desktop/PyraProjects` |
| Memory | Implemented | `memory/memory_manager.py` — unbounded store, prompt core + `recall_memory` |
| Undo | Implemented | `core/undo.py` for reversible file/settings ops |
| Confirm gate | Implemented correctly | `core/confirm.py` — UI-issued token, model cannot forge |
| Outcome contract | Implemented | `core/outcome.py` — done/unverified/failed/ask/started |
| Platform honesty | Implemented | `core/platform_support.py` — Wayland limits |
| Untrusted content | Implemented | markers + `prompt.txt` rules |
| Phone dashboard | Implemented | `dashboard/server.py` — pairing, rate limit, AES-GCM path |
| Avatar / HUD | Implemented | software-rendered head, visemes, video player |
| Plugins folder | Nearly empty here | Only `_template.py` — README lists many plugins **not present in this checkout** |

### 1.4 Partially implemented / conditional

| Area | Notes |
|---|---|
| Local engine | Code complete; depends on config + packages; default remains Gemini |
| Browser automation | Playwright-based; requires browsers installed; Wayland-independent for in-browser control |
| Computer control | Code present; **platform-limited on Wayland** |
| Dashboard HTTPS story | README documents HTTP-by-default vs TLS opt-in evolution; server module comments show dual-port design — treat as sensitive to version drift |
| Coding quality | `dev_agent` is multi-file but not a full engineering OS |

### 1.5 Experimental / unreliable on this host

| Area | Why |
|---|---|
| pyautogui desktop typing/click | Wayland + labwc; Mark’s own docs: success with no effect |
| Screen capture via mss | Same Wayland restriction |
| Window raise / focus | Restricted |
| Mark `.venv` | `pip` binary fails (`required file not found`); 1.3G tree present but interpreter path likely broken — **environment unhealthy until repaired** |
| Plugin ecosystem | README ≠ this tree |

### 1.6 Reuse / refactor / replace / leave alone

| Decision | Items |
|---|---|
| **Reuse directly** | `outcome.py`, `confirm.py`, `undo.py`, `platform_support.py`, action/plugin loader pattern, memory concepts, gemini ladder idea, untrusted wrappers, AGENTS.md threading rules |
| **Reuse via thin plugin** | Wake/voice/HUD; dashboard as remote wake; existing actions as optional Level-1 tools until Device Broker supersedes |
| **Refactor later** | Tool surface explosion for small local models (Mark already budgets tools); plaintext `api_keys.json` |
| **Replace (outside Mark)** | Flat single-agent tool loop as the “brain”; Desktop/PyraProjects as sole project model |
| **Leave untouched** | Avatar/viseme/echo/hotkey internals; Live receive loop; Qt UI structure — integrate externally |

### 1.7 Integration recommendation

Prefer **external Master service + one Mark plugin/action** (`agent_team` / `pyra_master`) calling HTTP. Do not embed orchestration in `main.py`. Align with Mark’s own design: actions self-describe; plugins are drop-in.

---

## 2. pukkyAI

### 2.1 Structure

| Item | Value |
|---|---|
| Path | `/home/hem/pukkyAI/pukky.py` (336 lines) |
| Model default | `qwen2.5:3b` via `PUKKY_MODEL` |
| Endpoint | Ollama `/api/chat` with tools |
| Tools | `run_command`, `read_file`, `hailo_run` |
| Max steps | 6 |
| History | In-process trim to ~17 messages |
| Safety | Regex block on wipe/shutdown-class commands |
| Hailo | `hailortcli run` HEF benchmarks; vision only |

### 2.2 Strengths

- Correct local agent loop shape (chat → tool_calls → results → answer).
- Explicit refusal of destructive shell patterns.
- Path jail for reads (`HOME`, hailo models, camera assets).
- Hailo integration that matches hardware reality (vision HEFs, not chat).
- Zero framework weight — suitable for Pi.

### 2.3 Limitations

- No durable memory / projects / multi-agent.
- Shell is nearly unbounded within the regex (still powerful).
- No outcome verification contract (exit code ≠ success semantics for apps).
- No MCP, no auth, no service API.
- Conversation amnesia on process exit.
- Not a GUI/browser controller.

### 2.4 Disposition decision

**C → B → A hybrid:** Treat pukky as a **disposable prototype whose working components are incorporated** into a new Master service, not as production code to grow in place.

| Keep | Evolve | Discard |
|---|---|---|
| Ollama tool loop | Into Master runtime | Standalone CLI as the product |
| Hailo tool idea | MCP `hailo_*` | Hardcoded HEF-only UX as the only lab tool |
| Blocklist mindset | Into Device Broker policy engine | Regex-only security |
| Small-model assumptions | Master role narrowing | Expecting 3B to write firmware |

**Justification:** Rewriting the 336-line loop inside a FastAPI service is cheaper than forcing Mark or OpenClaw to become the local master. pukky proves Ollama+tools on this Pi; it does not prove Project OS, permissions, or specialist orchestration.

---

## 3. Host configuration (verified)

### 3.1 Compute and storage

| Resource | Measured |
|---|---|
| SoC | Raspberry Pi 5, ARM Cortex-A76 × 4 @ up to 2.4 GHz |
| Arch | aarch64 |
| RAM | 7.9 GiB total; ~2.7 GiB available at audit (Cursor dominates) |
| Swap | 2 GiB zram, unused at sample |
| Root FS | 117G ext4 on mmcblk0; ~87G free |
| OS | Debian GNU/Linux 13 (trixie) |
| Kernel | 6.18.39+rpt-rpi-2712 |

### 3.2 Accelerators

| Device | Status |
|---|---|
| Hailo-8 | `/dev/hailo0` present; firmware 4.23.0; `hailort.service` active |
| HEFs | 18 models under `/usr/share/hailo-models`; H8/H8L variants present |
| GPU | VideoCore (not used for LLM); Cursor using render node |

### 3.3 AI stack

| Component | Status |
|---|---|
| Ollama | 0.14.0? (`ollama version is 0.40.14` reported — treat as installed 0.x); `systemd` **active**; listen `127.0.0.1:11434` |
| Models | `qwen2.5:3b` (1.9 GB), `gemma3:1b` (806 MB) |
| Ollama RSS idle | ~39 MB (model not necessarily loaded) |

### 3.4 Display / desktop control

| Item | Value |
|---|---|
| Session | **wayland** |
| Compositor | **labwc** (wlroots), `rpd-labwc` |
| `DISPLAY` | `:0` (XWayland likely available for some apps) |
| grim/slurp | Present (Wayland screenshot region tools) |
| xdotool/wmctrl/ydotool/wtype | **Missing** |
| Playwright CLI | Missing on PATH (may exist only in broken venv) |
| Portals | `wlr.portal`, `gtk.portal` active |
| wayvnc | **Active** on `*:5900` — remote desktop exists |

**Capability implication:** Full pyautogui-style control is **not** available in this session. Browser automation and process/xdg-open remain viable. VNC exists as a possible human observation path, not as a safe agent input synthesizer by itself.

### 3.5 Connectivity and peripherals

| Item | Status |
|---|---|
| Network | `wlan0` UP `192.168.0.116/24`; `eth0` DOWN; Tailscale UP |
| USB audio | TI PCM2902 codec present |
| Serial ACM/USB | **None** |
| Docker | 26.1.5 active; **no `docker compose` plugin** |
| Node/npm | **Not installed** |
| Python | System 3.13.5 |

### 3.6 Notable always-on services

ollama, docker, hailort, wayvnc, anydesk, tailscaled, lightdm — RAM competition with Master + Mark + n8n is real.

### 3.7 Commands for missing follow-ups (Phase 0)

```bash
# After explicit approval to run benchmarks (not done in this assignment):
ollama run qwen2.5:3b "ping"
# measure /api/chat with tools; record t/s, RSS, tool JSON validity

# Repair Mark venv (system-changing — needs approval):
cd ~/pyra/Mark-LIII && python3 -m venv .venv --clear && .venv/bin/pip install -r requirements.txt

# Compose for n8n (install needs approval):
sudo apt install docker-compose-plugin   # or pip/docker compose alternative

# Desktop strategy probes:
echo $XDG_SESSION_TYPE; grim /tmp/pyra-cap.png; ls -la /tmp/pyra-cap.png
```

---

## 4. Audit conclusions for architecture

1. Mark is a **production-grade face**, not the orchestration core.  
2. pukky is a **proof of local master loop**, not the OS.  
3. Host can run **small local models + Hailo vision + Docker**, but not a heavy multi-framework stack concurrently with Cursor/Mark.  
4. Wayland + missing input tools define Device OS Phase 3 scope.  
5. Broken Mark venv and missing Compose/Node are **deployment blockers**, not architecture blockers.  
6. Project OS, Agent Runtime, Device Broker, and Engineering OS are **greenfield** relative to both codebases.
