# Document 4 — Master AI Design

---

## 1. Role

The Master is the **central coordinator**, not the entire engineering brain.

It must:
- Interpret user intent (after STT in Mark, or text/API).
- Bind requests to a project (active, named, or create).
- Plan coarse work and select agents.
- Spawn/monitor specialists within policy.
- Validate structured results.
- Request human approval via Mark confirm bridge.
- Persist state through Project OS.
- Speak/report concise outcomes back to Mark.

It must not:
- Hold every tool on earth in one prompt.
- Silently flash hardware or send mail.
- Be the only place project truth lives (chat is ephemeral).

---

## 2. Process shape

```
Mark / CLI / Dashboard webhook
        │
        ▼
┌───────────────────────────┐
│ Pyra Master API           │
│ FastAPI + uvicorn         │
│ /v1/chat /v1/projects ... │
└─────────────┬─────────────┘
              │
     ┌────────┼────────┐
     ▼        ▼        ▼
 LocalLLM  Orchestrator  ProjectOS client
 (Ollama)  (task graph)  (SQLite/FS)
     │        │
     ▼        ▼
 ModelRouter  AgentRuntime + DeviceBroker MCP
```

**Language:** Python 3.13 — matches Mark/pukky/host; MCP Python SDK; Pydantic; FastAPI already familiar from Mark dashboard.  
**Rejected for Master core:** Node (not installed), Go rewrite (no reuse of pukky/Mark patterns), embedding inside Qt process (threading/lifecycle coupling).

---

## 3. Local intelligence boundaries

| Decision | Owner |
|---|---|
| Intent class, project id, whether to ask user | Master LLM + validators |
| Task graph edges / retries / timeouts | Orchestrator (deterministic) |
| Project metadata mutations | Project OS API |
| Tool execution allow/deny | Device Broker (non-LLM) |
| Specialist technical content | Specialist agents |
| Irreversible Level 2–3 | Human via Mark confirm |
| Workflow steps for mail/GH | n8n |

### Anti-recursion rule

Specialists may request help only by creating a **Project OS task** with `needs_agent=<role>` and `parent_task_id`. Orchestrator caps depth (default **2**) and fan-out. No agent may directly invoke another agent’s LLM session without Orchestrator.

---

## 4. Request pipeline

```
1. Ingest (Mark message / CLI)
2. Load active project context pack (bounded)
3. Local Master model → structured Intent
   Intent = {
     kind, project_ref, urgency,
     needs_cloud, agent_hints[],
     user_question?, risk_level
   }
4. Validate Intent (Pydantic); on failure → clarify
5. Orchestrator expands to Tasks (or calls single tool)
6. Execute:
   - local tool via Broker
   - OR specialist run
   - OR n8n workflow
7. Validate outputs against OutputContract
8. Write Project OS events + checkpoint if needed
9. Return SpeechPayload + MachinePayload to Mark
```

---

## 5. Model Gateway / hybrid routing

```
Intent.needs_cloud or task.complexity
        │
        ├─ false → Ollama master / tiny helpers
        └─ true  → Provider ladder
                    1. configured primary (e.g. Gemini)
                    2. secondary (OpenRouter/Anthropic/OpenAI)
                    3. fail → degrade to local summary + ask user
```

| Concern | Design |
|---|---|
| Timeouts | Per-call deadlines (Mark gemini.py lesson) |
| Rate limits | Cooldown rungs |
| Cost | Tag tasks with budget class; log tokens |
| Failures | Retry idempotent reads; never auto-retry Level 3 |
| Abstraction | `CompletionClient` interface; Ollama + OpenAI-compat implementations |

**Local default tasks:** intent, project switch phrasing, status, short plan, tool selection among ≤12 tools, approval narration.  
**Cloud tasks:** architecture, datasheet reasoning, large code edits, deep debug.

---

## 6. Context pack (what Master sees)

Never dump full history. Pack:

1. User identity prefs (from Mark memory sync or Pyra global memory) — small  
2. Active project: `PROJECT.md` summary, state, open tasks (top N)  
3. Last checkpoint digest  
4. Relevant decision records (IDs)  
5. Capability/limits string (Wayland, no serial, etc.)  
6. Current approval banner state  

Long artifacts retrieved via tools (`project_read`, `recall`).

---

## 7. Orchestrator

Minimal durable engine:

- Task table in SQLite (`queued|running|blocked|done|failed|cancelled`)  
- Workers: asyncio + process pool for long jobs  
- Parallelism: default 1 heavy + 1 light on Pi; configurable  
- Checkpoint after each task terminal state  
- Pause project → cancel or park running tasks with reason  

**LangGraph:** optional later adapter implementing the same Task semantics; not required for Phase 1.

---

## 8. Mark integration contract

Mark plugin calls:

`POST /v1/interact`  
```json
{
  "source": "mark",
  "text": "switch to flight computer",
  "session_id": "...",
  "mark_confirm_available": true
}
```

Response:
```json
{
  "speech": "Switching to flight computer. Resuming firmware bring-up.",
  "hud": {"title": "...", "body": "..."},
  "needs_confirm": null,
  "project_id": "flight-computer"
}
```

When Master needs Level 2–3 approval, return `needs_confirm` and Mark shows existing confirm UI; on confirm, Mark calls `POST /v1/approvals/{id}/resolve`.

---

## 9. Persistence & recovery

- Master is stateless regarding project truth.  
- On restart: reload SQLite; mark interrupted `running` tasks as `interrupted`; Master announces recovery on next interact.  
- ACP/coding sessions: store external session ids in Project OS; resume if agent supports; else rehydrate from checkpoint notes.

---

## 10. pukky mapping

| pukky | Master |
|---|---|
| `chat()` | Model Gateway Ollama client |
| `TOOLS` | Dynamic MCP tool view (filtered) |
| `run_tools` | Broker invoke |
| `MAX_STEPS` | Orchestrator step budget |
| `BLOCKED` regex | Broker policy (stronger) |
| CLI loop | `/v1/interact` + Mark |
