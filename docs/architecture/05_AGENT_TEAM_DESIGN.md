# Document 5 — Agent Team Design

> **Baseline note (2026-11-10):** Authoritative Agent Runtime design is  
> [`technology-adoption/05_AGENT_RUNTIME_DESIGN.md`](technology-adoption/05_AGENT_RUNTIME_DESIGN.md).  
> Specialists use **PydanticAI** behind Agent Runtime; tools via **BrokerClient** (not MCP-mandatory).  
> LangGraph is selective durable orchestration only (ADR-002). Start with a **small** specialist roster.

---

## 1. Standard agent interface

Every specialist implements:

```text
AgentManifest:
  id, version, title, description
  input_schema (JSON Schema / Pydantic)
  output_schema
  default_provider (local|cloud|acp)
  tool_allowlist[]          # Broker capability / tool names (BrokerClient)
  max_level (0-3)           # Device Broker ceiling (not agent-escalable)

  timeout_s, max_retries
  memory_scopes[]           # project|agent|none
  concurrency_class         # light|heavy
```

```text
AgentRunRequest:
  project_id, task_id, goal, artifacts[], parent_task_id?
AgentRunResult:
  status: done|failed|blocked|needs_approval
  summary, artifacts[], decisions[], next_tasks[], evidence[]
```

Adding an agent = drop manifest + runner module; Orchestrator discovers via registry. **Master core unchanged.**

---

## 2. Core roster

| ID | Responsibility | Provider (Phase 4) | Tools (max level) | Validation |
|---|---|---|---|---|
| `master` | Coordination only | Local Ollama | project_*, spawn, ask_user (L1) | Intent schema |
| `project_mgr` | WBS, milestones, risks, assignments | Cloud | project_tasks_*, docs write (L1) | Plan has milestones + owners |
| `research` | Web/docs/datasheets | Cloud | web_search, fetch, project_docs (L0–1) | Sources cited; untrusted wrap |
| `systems` | Requirements, architecture, ICD, risks | Cloud | docs, diagrams (L1) | Req/ICD artifacts exist |
| `hardware` | Parts, BOM, bring-up plan, schematic assist | Cloud | docs, kicad_cli later (L1) | Explicit “needs human EE review” |
| `firmware` | Drivers, RTOS, build/flash requests | Cloud / ACP | repo, build, serial, flash (L1–3) | Build log + evidence objects |
| `software` | Host apps, CI, tests | Cloud / ACP | repo, git, test (L1–2) | Tests executed or justified skip |
| `testing` | Plans, automation, HIL scripts | Cloud | repo, test runners, lab read (L1) | Traceability to requirements |
| `lab` | Serial, instruments, Hailo vision | Local+tools | serial, hailo, shell L1 (L2 gated) | Raw logs attached |
| `docs` | Specs, manuals, release notes | Cloud | docs only (L1) | Links to source artifacts |
| `ops` | Mail, GH, calendar, bookings | n8n-first | n8n_* only (L2 gated send) | Workflow execution id |
| `desktop` | Apps/browser/UI | Local | browser, open_app (L1–2) | outcome status≠assumed |

Agents may be **dormant** until Project Manager assigns them.

---

## 3. Collaboration model (hybrid)

**Primary:** Master-mediated delegation via Project OS task queue.  
**Secondary:** Shared artifacts in `projects/<id>/artifacts/` and `workspace/`.  
**Tertiary:** ACP sessions for long coding threads.  
**Not primary:** free-form agent-to-agent chat (hard to audit).

Example flow:

1. `systems` writes `architecture.md` → artifact  
2. Task created: `hardware.review_interfaces` with input artifact id  
3. `firmware` blocked until `bringup.power_ok` evidence exists  
4. File leases: `project_file_lock(path, agent_id, ttl)` prevents silent overwrite  

---

## 4. Per-agent session handling

| Aspect | Policy |
|---|---|
| Memory | Project memory authoritative; agent scratchpad optional JSONL |
| Resume | Reload last `AgentRunResult` + task; ACP `session/resume` when available |
| Retry | Transient provider errors: exponential backoff ×3; logic failures: escalate to Master |
| Timeout | Default 10 min cloud; 60 min ACP coding; lab interactive sessions explicit |
| Failure | `blocked` with reason; never mark project done |

---

## 5. Cloud vs local vs ACP

| Work | Runtime |
|---|---|
| Routing, status | Local Master |
| Design docs, reviews | Cloud specialist |
| Multi-file code in workspace | Cloud specialist early; **ACP coding agent** later |
| Serial listen / hailo | Lab agent local tools |
| Email send | ops → n8n |

---

## 6. System prompts (design rules, not final text)

Each agent prompt must include:
- Role and hard tool limits  
- Output schema reminder  
- Untrusted content rules  
- “Do not claim hardware success without evidence object”  
- Project id and non-goals  

Prompts live in `agent-os/agents/<id>/SYSTEM.md` versioned in git.

---

## 7. Parallelism on Pi

- Max **one** `heavy` agent (cloud coding / large context)  
- Max **two** `light` agents (research fetch, docs)  
- Lab interactive exclusive lock on serial port  

---

## 8. Mapping to user-visible commands

| User says | Master does |
|---|---|
| “Ask the systems engineer to review…” | Task → `systems` with review goal |
| “Continue firmware…” | Resume `firmware` session / next open firmware task |
| “What were we doing in bring-up?” | Read project memory + lab evidence; summarize locally |
