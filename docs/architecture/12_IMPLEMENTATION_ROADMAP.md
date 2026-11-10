# Document 12 — Implementation Roadmap

> **SUPERSEDED FOR SEQUENCING (2026-11-10):**  
> Authoritative phase sequence is in [`PYRA_ARCHITECTURE_BASELINE.md`](PYRA_ARCHITECTURE_BASELINE.md) §11.7 and  
> [`technology-adoption/10_UPDATED_IMPLEMENTATION_ROADMAP.md`](technology-adoption/10_UPDATED_IMPLEMENTATION_ROADMAP.md).  
> Phases 0–4 are **complete** in code (including Engineering OS discovery). This file is retained as historical planning.

**Constraint (historical):** No coding until architecture review sign-off.  
**Critical path (historical):** Phase 0 → 1 → 2 → 3 → 5 (Mark) with 4/6 parallelizable after 1–2.

---

## Phase 0 — Discovery & feasibility

| | |
|---|---|
| Objective | Close unknowns; decide X11 vs Wayland strategy; fix env blockers list |
| Dependencies | Owner approvals for benchmarks/installs |
| Tasks | Benchmark Ollama tool JSON on qwen2.5:3b/1.5b/7b; repair Mark venv plan; Compose install plan; serial HW inventory; confirm Hailo HEF run |
| Deliverables | Benchmark table; Decision: desktop strategy; updated risk register |
| Tests | Documented commands reproduce |
| Acceptance | Written go/no-go for Phase 1 |
| Complexity | L |
| Resources | Temporary model RAM spikes |

---

## Phase 1 — Pyra Core (Master)

| | |
|---|---|
| Objective | Master API + local Ollama + Intent schema + Model Gateway stub |
| Components | `agent-os/master`, CompletionClient, `/v1/interact` |
| Tech | Python, FastAPI, Pydantic, Ollama |
| Deliverables | systemd unit; CLI client; healthz |
| Tests | Intent classification suite (20 utterances); failure if Ollama down returns clear error |
| Acceptance | Local-only interact works without Mark |
| Complexity | M |

---

## Phase 2 — Project OS

| | |
|---|---|
| Objective | Multi-project create/switch/checkpoint/resume |
| Dependencies | Phase 1 |
| Tech | SQLite + FS layout |
| Deliverables | project CLI; DB migrations; context pack builder |
| Tests | Create A/B; switch; kill Master; resume state intact |
| Acceptance | User never loses notes/tasks across switch |
| Complexity | M |

---

## Phase 3 — Device OS

| | |
|---|---|
| Objective | Broker MCP: fs, shell, proc, browser(Playwright), outcome+levels |
| Dependencies | Phase 1; Playwright install approval |
| Deliverables | MCP servers; audit log; capability probe at boot |
| Tests | Path jail escape attempts fail; Wayland desktop ops return `failed/unsupported` honestly; browser navigate+fill demo |
| Acceptance | Matrix matches Doc 7 |
| Complexity | H |

---

## Phase 4 — Agent Team

| | |
|---|---|
| Objective | Specialist runners + cloud providers + task delegation |
| Dependencies | Phases 1–2; partial 3 |
| Deliverables | Manifest registry; research/systems/firmware stubs; depth limit |
| Tests | Parallel light agents; recursion cap; file lock conflict |
| Acceptance | “Ask systems to review” creates artifact |
| Complexity | H |

---

## Phase 5 — Mark-LIII Integration

| | |
|---|---|
| Objective | Plugin/action → Master; speech/HUD; confirm bridge |
| Dependencies | Phase 1 (+2 preferred) |
| Deliverables | `plugins/pyra_master.py` (or actions); no main.py fork |
| Tests | Wake → interact → project switch by voice |
| Acceptance | Mark remains usable if Master down (graceful message) |
| Complexity | M |

---

## Phase 6 — Automation (n8n)

| | |
|---|---|
| Objective | n8n up; 3 MCP workflows; ops agent |
| Dependencies | Docker Compose; Phase 1 |
| Deliverables | Compose file; workflow git exports; auth |
| Tests | Create GH issue / mail draft dry-run |
| Acceptance | Master invokes workflow and stores execution id |
| Complexity | M |

---

## Phase 7 — Embedded Engineering

| | |
|---|---|
| Objective | Templates, build/flash/serial evidence loop |
| Dependencies | Phases 2–4; hardware |
| Deliverables | Zephyr/ESP-IDF template; lab MCP; bring-up checklist engine |
| Tests | Hello-world build; simulated evidence; real UART when board present |
| Acceptance | Build≠hardware-ok enforced in reports |
| Complexity | H |

---

## Phase 8 — Advanced

ACP coding agents; optional OpenHands sandbox; Hailo vision lab demos; vector datasheet search; LangGraph evaluation for long pipelines.

---

## Phase 9 — Hardening

Security review; resource governor; backup drills; chaos (kill Mid-task); docs freeze; v1.0.

---

## Definition of Done (platform v1)

1. Voice/text create & switch projects with continuity.  
2. Master local for routing when Ollama up; cloud optional.  
3. ≥3 specialists usable via API.  
4. Broker enforces levels; L3 needs human.  
5. Browser automation path works.  
6. Desktop limitations honest on Wayland.  
7. ≥1 n8n workflow via MCP.  
8. Embedded template + evidence-based bring-up checklist.  
9. Audit log for tool calls.  
10. Mark integration without forking Live loop.

---

## Testing strategy

| Layer | Method |
|---|---|
| Unit | Pydantic contracts, policy engine, Project OS |
| Integration | Master↔Broker↔Ollama |
| Voice E2E | Scripted Mark plugin tests |
| Security | Jail/allowlist fuzz |
| Embedded | Hardware-in-loop when available; fixtures otherwise |
