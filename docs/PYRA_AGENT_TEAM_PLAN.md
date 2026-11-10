# Pyra Mark-LIII → Agent Team Platform

> **Superseded for architecture decisions.**  
> **Authoritative freeze:** [`architecture/PYRA_ARCHITECTURE_BASELINE.md`](architecture/PYRA_ARCHITECTURE_BASELINE.md) (v1.0).  
> Index: [`architecture/00_INDEX_AND_EXECUTIVE_SUMMARY.md`](architecture/00_INDEX_AND_EXECUTIVE_SUMMARY.md).  
> This file is retained as the initial proposal; “MCP everywhere as tool bus” wording is **superseded** by BrokerClient (internal) + MCP (external) — ADR-001.

**Working title:** Pyra Agent OS (Mark-LIII as the face; a multi-agent brain behind it)

**Device:** Raspberry Pi 5 (`hem@raspberrypi`), ~8 GB RAM, aarch64, Hailo-8 (HailoRT 4.23), Ollama installed, Docker available, Wayland session today.

**Date:** 2026-11-09

---

## 1. What you have today (honest baseline)

### 1.1 Mark-LIII (folder name) = Mark LVI codebase

This is **not** an empty shell. It is a mature **voice personal assistant** with:

| Layer | What exists | Gap vs your goal |
|---|---|---|
| Wake / voice I/O | “Hey Pyra”, PTT, Whisper/Piper optional, Gemini Live default | Fine as the **operator interface** |
| Tool dispatch | Auto-discovered `actions/*.py` + `plugins/*.py` | Tools are **flat skills**, not a team |
| Device control | `open_app`, `computer_control`, `browser_control` (Playwright), files, settings | **Wayland blocks** type/click/screenshot; honesty exists in `platform_support.py` |
| Coding | `dev_agent` (build/improve/status on Desktop/PyraProjects) | One coding worker, **no project graph**, no multi-role engineering pipeline |
| Memory | `memory/long_term.json` + recall | Facts about you, **not** multi-project workspaces with pause/resume |
| Engine choice | Gemini Live **or** STT→LLM→TTS via `providers/` | Good for hybrid local/cloud |
| Dashboard | Phone QR dashboard | Remote wake/command entry point |

**Verdict:** Mark-LIII is an excellent **front door + verified computer tools**. It does **not** yet orchestrate a team, switch projects, or do full embedded engineering as a pipeline.

### 1.2 pukkyAI (`~/pukkyAI/pukky.py`)

A **starter local agent**, not a product:

- Ollama chat + tools (`run_command`, `read_file`, `hailo_run`)
- Default model `qwen2.5:3b`, max 6 tool steps
- Hard blocks for wipe/shutdown-class shell
- Hailo used for **vision HEFs only** (YOLO etc.), not as the chat LLM
- No memory across sessions beyond a trimmed chat list, no MCP, no multi-agent, no GUI control

**Verdict:** Perfect seed for the **local Master Agent loop** (plan → tool → observe → answer). Keep the shape; replace the guts with MCP-backed tools + project state.

### 1.3 This machine’s hard constraints

1. **Wayland** (`XDG_SESSION_TYPE=wayland`) — Mark itself documents that pyautogui/mss/window-raise are unreliable or no-ops. Full “open any app, fill forms, drive the desktop” needs either:
   - log into an **X11/Xorg** session, or
   - a Linux desktop-control path that works under Wayland (portal / compositor-specific / dedicated browser-only automation via Playwright).
2. **8 GB RAM + 4 cores** — a strong local *orchestrator* (1.5B–3B–7B quantized) is realistic; a 70B “do everything” model on-device is not. Specialist heavy reasoning should stay **API** (or a bigger box later).
3. **Hailo-8** — excellent for **vision / detection / pose**, and there are community paths to small Hailo-served LLMs; do not assume every Ollama GGUF magically runs on Hailo. Plan: CPU/Ollama for agent brain; Hailo for perception tools.
4. **License** — upstream Mark is **CC BY-NC 4.0**. Fine for personal use; if you productize commercially, fork strategy / rewrite boundary matters.

---

## 2. Target vision (one sentence)

**Pyra wakes on your command, owns the Linux device, runs a local Master Agent that delegates to specialist agents (API or local), persists many parallel projects, and uses n8n for deterministic automations — covering full embedded engineering plus general life/ops tasks.**

Summary flow you asked for:

```
You → wake Pyra → Master Agent (local)
        ├─ Project Manager (create / switch / resume)
        ├─ Specialist Agents (API for now)
        ├─ Device MCP tools (shell, files, browser, desktop, git, serial, …)
        └─ n8n workflows (mail, cab, webhooks, scheduled ops)
```

---

## 3. Architecture (layers)

```
┌─────────────────────────────────────────────────────────────┐
│  A. OPERATOR SURFACE                                        │
│     Mark-LIII HUD + wake word + phone dashboard + CLI       │
└───────────────────────────┬─────────────────────────────────┘
                            │ intents / voice / text
┌───────────────────────────▼─────────────────────────────────┐
│  B. MASTER AGENT (local) — evolution of pukky               │
│     plan · route · confirm · consolidate · speak            │
│     models: Ollama (qwen2.5:3b → 7b) + optional cloud boost │
└─────────┬─────────────────┬─────────────────┬───────────────┘
          │                 │                 │
          ▼                 ▼                 ▼
┌─────────────────┐ ┌───────────────┐ ┌───────────────────────┐
│ C. PROJECT OS   │ │ D. AGENT TEAM │ │ E. AUTOMATION BUS     │
│ workspaces,     │ │ specialists   │ │ n8n + webhooks + cron │
│ artifacts,      │ │ via API/ACP   │ │ MCP Server Trigger    │
│ checkpoints     │ │ MCP tools     │ │ Gmail/GitHub/cabs…    │
└────────┬────────┘ └───────┬───────┘ └───────────┬───────────┘
         │                  │                     │
         └──────────────────┼─────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  F. DEVICE CONTROL PLANE (MCP servers on this Pi)           │
│     filesystem · shell · browser · desktop · git · serial   │
│     gpio/i2c/spi · probe · build · flash · hailo vision     │
│     outcome contract: done | unverified | failed | ask      │
└─────────────────────────────────────────────────────────────┘
```

### Why these protocols

| Protocol | Role in Pyra |
|---|---|
| **MCP** (Model Context Protocol) | Standard **tool bus**. Master + specialists call the same device tools. n8n exposes workflows as MCP tools; Pyra can also expose device MCP to Cursor/Claude. |
| **ACP** (Agent Client Protocol) | Standard **IDE ↔ coding agent** session protocol (JSON-RPC). Use when a specialist is “open Cursor/Claude Code/OpenCode against this repo” rather than inventing another chat API. |
| **OpenAI-compatible HTTP** | How Ollama / Gemini / Groq / OpenRouter all look the same to `providers/` and pukky-style loops. |
| **n8n webhooks + MCP** | Deterministic multi-step life/ops flows the LLM should not re-invent every time. |

Do **not** invent a fourth proprietary RPC if MCP already fits. Extend Mark’s `actions/` so each heavy skill is a thin wrapper over an MCP tool (same outcome vocabulary Mark already uses).

---

## 4. Agent team (roles)

Start with a **small roster**. Each agent gets **only the tools it needs** (platform-enforced, not prompt-only — same lesson as Pi multi-agent architectures and Mark’s own tool budgets).

| Agent ID | Job | Backend (phase 1) | Tools |
|---|---|---|---|
| `master` | Wake, clarify, route, confirm dangerous acts, report | **Local Ollama** (pukky lineage) | project_*, session_*, ask_user, spawn_agent |
| `systems` | Requirements, block diagrams, interfaces, risk | Cloud API (Gemini/Claude/GPT) | docs, drawio/mermaid, web_search |
| `hardware` | Schematics review, BOM, bring-up checklists, probe plans | Cloud API | docs, web_search, (later) KiCad MCP |
| `firmware` | Bare-metal / RTOS / HAL, linkerscripts, flash | Cloud API + ACP coding agent | repo MCP, serial, build, flash |
| `software` | Host apps, drivers, tests, CI | Cloud API + ACP | repo MCP, git, test runners |
| `lab` | Oscilloscope notes, logic analyzer, Hailo vision checks | Local + Hailo | shell, hailo_run, camera, serial |
| `ops` | Mail, calendar, GitHub hygiene, bookings, reminders | Mostly **n8n** | n8n MCP tools only |
| `desktop` | Open apps, browse, type, fill forms, show pages | Local device MCP | browser, desktop (X11), open_app |

**Routing rule (Master):**

```
if task < 3 tool calls and local → master does it
if deterministic life/ops → n8n / ops
if multi-file code in a project → firmware|software via ACP or repo agent
if irreversible (flash, rm, power, buy, send) → confirm gate (reuse Mark confirm.py)
if project switch → Project OS only (never lose prior checkpoint)
```

---

## 5. Project OS (the multi-project requirement)

This is the piece Mark and pukky both lack.

### 5.1 Storage layout

```
~/PyraWork/
  registry.json                 # list of projects + active id
  projects/
    <project_id>/
      PROJECT.md                # goal, constraints, status
      state.json                # phase, active agent, blockers
      memory.jsonl              # append-only decisions / findings
      artifacts/                # schematics exports, logs, images
      workspace/                # git repo or linked path
      agents/
        firmware.session.json   # resumable chat / ACP session ids
        software.session.json
      checkpoints/
        2026-11-09T22-00Z.json
```

### 5.2 Master tools

- `project_create(name, goal, template?)`
- `project_list()`
- `project_switch(id)` — checkpoint current, load target
- `project_status(id?)`
- `project_continue(id?)` — resume last incomplete agent turn
- `project_note(text)` — write to memory.jsonl
- `artifact_add(path, kind)`

### 5.3 Switching semantics

1. Flush current agent session summary → checkpoint.
2. Persist open file paths / branch / serial port / n8n run ids.
3. Load target project prompt slice into Master context (not whole history).
4. On “continue”, reload last agent session via ACP `session/resume` or stored thread id.

Voice UX examples:

- “Hey Pyra, new project: BLE soil sensor on ESP32-C3”
- “Switch to motor driver board”
- “Where did we leave firmware bring-up?”

---

## 6. Device access (complete control)

### 6.1 Immediate (works even on Wayland)

| Capability | Mechanism |
|---|---|
| Shell / packages / services | MCP `shell` with allow/deny lists (graduate from pukky `run_command`) |
| Files under home + project roots | MCP `fs` |
| Browser open + automate | Playwright (`browser_control` already in Mark) — **preferred for “fill text / show webpage”** |
| GitHub | `gh` CLI + n8n GitHub nodes |
| Voice / HUD content | existing Mark `player.show_content` / `show_video` |
| Hailo vision | pukky `hailo_run` promoted to MCP |
| Serial / USB | `pyserial` MCP (`/dev/ttyACM*`, baud, log) |

### 6.2 Full desktop puppetry (open any app, type anywhere)

**Required platform choice:** prefer **X11 session** for Mark’s pyautogui path, *or* invest in a Wayland-native controller later.

Phased approach:

1. **Phase A:** Playwright + `xdg-open` + process control (good enough for web + many Electron apps).
2. **Phase B:** X11 session + Mark `computer_control` / `open_app` / `desktop`.
3. **Phase C:** Optional dedicated “desktop MCP” (ydotool / wtype / compositor portals) if you stay on Wayland.

Reuse Mark’s **outcome contract** everywhere: `done | unverified | failed | ask | started`. Never let an agent claim success from a return code alone.

### 6.3 Embedded engineering tool surface

Expose as MCP tools (thin wrappers):

- `build_west` / `idf.py` / `pio` / `make`
- `flash_probe` (OpenOCD, probe-rs, esptool)
- `serial_session`
- `git_*`
- `datasheet_fetch` (untrusted-content wrapped — Mark already has this pattern)
- `schematic_export` / KiCad CLI when installed
- `n8n_run_workflow`

---

## 7. n8n’s place

n8n is the **deterministic automation plane**, not the brain.

| Pattern | Use |
|---|---|
| n8n as **MCP server** | Master calls curated workflows: `book_cab`, `draft_email`, `triage_inbox`, `create_github_issue` |
| n8n as **MCP client** | Rare: n8n agent node calling Pyra device MCP for “on this Pi, run bring-up script” |
| Instance MCP | Let Cursor edit n8n workflows while you build them |
| Schedules / webhooks | Morning brief, repo watchers, CI failure → Pyra HUD alert |

Recommended stack on this Pi (Docker):

- `n8n` + `postgres`
- Start with 5 workflows only (mail draft, GH issue, reminder, webhook→Pyra, cab/booking stub)
- Auth on every MCP URL

Reference patterns: OpenClaw↔n8n stacks, n8n MCP Server Trigger, n8n instance MCP.

---

## 8. Local Master AI plan

### 8.1 Near-term (reuse pukky)

1. Keep Ollama on CPU with `qwen2.5:3b` (or 1.5B if latency hurts).
2. Narrow the Master’s job: **JSON route + short speech**, not writing firmware itself.
3. Split roles inside one small model only if needed: planner / judge (see Pi agentic blogs) — one checkable JSON output per call.
4. Route hard reasoning to cloud specialists.

### 8.2 Hailo

- Keep vision HEFs via `hailo_run`.
- Treat Hailo-LLM experiments as **optional acceleration** for tiny models once stable; do not block the Agent OS on it.
- Monitor `/dev/hailo0` (logs show intermittent open failures historically).

### 8.3 Mark integration

Two integration options:

**Option 1 — Preferred:** Master runs as a **daemon**; Mark gains one action `agent_team` that forwards user intents and speaks results. Mark remains the voice/HUD.

**Option 2:** Point Mark’s local engine (`providers/`) at the Master’s OpenAI-compatible endpoint so the same voice loop drives the team. Harder: tool budget + small-model limits Mark already measured.

Start with Option 1.

---

## 9. Embedded engineering lifecycle (how the team works a project)

| Phase | Owner | Outputs |
|---|---|---|
| 0. Intake | master | PROJECT.md, success criteria |
| 1. System eng | systems | architecture.md, interface table, risks |
| 2. Hardware plan | hardware | block diagram, BOM draft, bring-up matrix |
| 3. Repo scaffold | software/firmware | workspace git, CI skeleton |
| 4. Bring-up | lab + firmware | power rails checklist, first blink / USB enum |
| 5. Firmware loop | firmware (+ ACP) | HAL, drivers, flash, serial logs |
| 6. Host/tools | software | flash scripts, tests, dashboards |
| 7. Integration | master + all | checkpoint reviews |
| 8. Closeout | master | artifact pack, lessons → project memory |

Human gates: buy parts, high-voltage, mass erase, production fuse bits — always Mark `confirm`.

---

## 10. Existing solutions to borrow (not blindly copy)

| Project | Steal this | Avoid |
|---|---|---|
| **Mark LVI** | Voice, tools, outcomes, undo, confirm, memory UX | Assuming one flat tool list scales to a team |
| **pukkyAI** | Local tool loop, Hailo hook, safety regex | Shell-as-only-tool forever |
| **OpenClaw + n8n** | Orchestrator + ops specialist + MCP registry | Cloud-only default; Docker RAM cost on 8 GB |
| **OpenHands** | MCP SSE/HTTP/stdio tool attachment | Heavyweight for Pi as the always-on master |
| **ACP agents** (Gemini CLI, OpenCode, Copilot, …) | Coding sessions with resume | Using ACP for non-coding ops |
| **Pi multi-agent writeups** | Tool scoping per agent; parallel specialists | Over-delegation for tiny tasks |
| **Hailo + Ollama blogs** | Hybrid local tiny + cloud smart | Expecting 8B+ quality on Hailo-8 |

---

## 11. Execution roadmap

### Phase 0 — Foundation (1–2 weeks)

- [ ] Decide display: switch daily driver to **X11** for full desktop control, or accept Playwright-first on Wayland.
- [ ] Stabilize Ollama model pull; systemd enable; measure tokens/s for 1.5B vs 3B.
- [ ] Confirm Hailo `/dev/hailo0` reliability; wrap pukky `hailo_run` tests.
- [ ] Create `~/PyraWork/` layout + `registry.json` schema.
- [ ] Run n8n in Docker with Postgres; lock down auth.

### Phase 1 — Master + Project OS (2–3 weeks)

- [ ] Refactor pukky → `pyra-master` service (HTTP + CLI).
- [ ] Implement project_* tools + checkpoint/switch.
- [ ] MCP server: `fs`, `shell` (allowlist), `hailo`.
- [ ] Mark action `agent_team` → master HTTP.
- [ ] Voice demos: create / switch / status / continue.

### Phase 2 — Specialist APIs + n8n (2–4 weeks)

- [ ] Agent runner: spawn cloud specialist with scoped tools + project context pack.
- [ ] Wire 3–5 n8n workflows as MCP tools (mail, GH, reminder).
- [ ] Desktop/browser MCP → “open page, fill field, show on HUD”.
- [ ] Safety: confirm gate for outbound messages / spends / flashes.

### Phase 3 — Embedded depth (ongoing)

- [ ] Serial + flash + build MCP tools.
- [ ] ACP bridge for firmware/software agents against `workspace/`.
- [ ] Templates: ESP-IDF, Zephyr, STM32Cube, Pi HAT bring-up.
- [ ] Lab agent + Hailo camera checks.
- [ ] Parallel specialists with Master consolidation.

### Phase 4 — Hardening

- [ ] Audit logs per project; secret vault (not plaintext next to Mark keys).
- [ ] Resource governor (RAM/CPU) so Mark voice + Ollama + n8n coexist.
- [ ] Backup `PyraWork` + n8n; disaster resume.
- [ ] Optional: expose Pyra device MCP to Cursor on the LAN (SSH tunnel).

---

## 12. Suggested repo layout (new code beside Mark)

```
/home/hem/pyra/
  Mark-LIII/                 # voice face (upstream-based)
  docs/PYRA_AGENT_TEAM_PLAN.md
  agent-os/                  # NEW
    master/                  # pukky evolution
    mcp/
      device_fs/
      device_shell/
      device_browser/
      device_lab/            # serial, hailo, flash
    project_os/
    agents/                  # specialist runners (API)
    acp_bridge/              # optional coding agent host
    integrations/
      n8n/
      mark_action/           # plugin dropped into Mark plugins/
  PyraWork/ → ~/PyraWork     # runtime data (not in git)
```

Keep Mark upgrades mergeable: prefer a **plugin** into Mark over deep forks of `main.py`.

---

## 13. Success criteria (definition of done)

1. “Hey Pyra, start project X” creates a workspace and a plan artifact.
2. Work can pause; “switch to Y” then “continue X” restores state without amnesia.
3. Master stays local; specialists may be API; tools hit **this** Linux device.
4. Browser automation can open a URL, fill a field, and show content on the HUD.
5. An embedded path exists: plan → repo → build → flash → serial observe → note in project memory.
6. At least one life workflow (mail or GitHub) runs via n8n MCP, not ad-hoc LLM scripting.
7. Irreversible actions always go through a human confirm control.

---

## 14. Risks and decisions you must make

| Decision | Options | Recommendation |
|---|---|---|
| Desktop control | Stay Wayland vs X11 | **X11 for Phase 1–2** if “complete access” is non-negotiable |
| Master model | 1.5B vs 3B vs 7B | Start **3B**; drop to 1.5B if RAM fights n8n |
| Where n8n lives | Same Pi vs NAS/PC | Same Pi only if workflows stay light; else secondary host |
| Coding agent | Homegrown vs ACP (OpenCode/Claude Code/…) | **ACP for coding**; homegrown Master for routing |
| Cloud vendor | Gemini (already in Mark) vs Claude vs OpenRouter | Reuse Mark ladder for specialists first |
| Security | Full root shell vs allowlists | Allowlist + confirm; expand deliberately |

---

## 15. First concrete build order (when you say go)

1. `agent-os/project_os` skeleton + CLI.
2. `pyra-master` HTTP wrapping pukky with `project_*` + MCP client.
3. MCP `device_shell` + `device_fs` with Mark-style outcomes.
4. Mark `plugins/agent_team.py` calling master.
5. Docker Compose for n8n; one webhook workflow calling back into master.
6. X11 session check + Playwright “show this page” demo.

---

*This document is the planning baseline. Implementation should follow the roadmap phases; do not try to build the full embedded factory before Project OS + Master routing work.*
