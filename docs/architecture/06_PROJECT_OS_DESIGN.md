# Document 6 — Project OS Design

> **Baseline note (2026-11-10):** Project OS remains the **authoritative** persistent project-state system. Agent conversation history must not substitute for it. See [`PYRA_ARCHITECTURE_BASELINE.md`](PYRA_ARCHITECTURE_BASELINE.md).

---

## 1. Purpose

Authoritative, durable engineering workspace manager. Chat history is **not** the project.

---

## 2. Storage choice

**Combination: filesystem + SQLite**

| Store | Contents |
|---|---|
| `~/PyraWork/pyra.db` | Registry, tasks, events, locks, approvals, indexes |
| `~/PyraWork/projects/<id>/` | Human-readable artifacts, repos, sessions, checkpoints |
| Optional later | Vector index under project for datasheets |

**Rejected:** Postgres for core (extra daemon); “JSON files only” (weak querying); “all in vector DB” (bad for tasks/state).

### Layout

```
~/PyraWork/
  pyra.db
  global/
    user_memory.json
    pyra_memory.json
  projects/
    <project_id>/
      PROJECT.md
      state.json          # cache of DB row for humans/git
      memory.jsonl        # append-only notes/decisions
      tasks/              # optional markdown mirrors
      artifacts/
      workspace/          # git root or gitlink
      agents/
        <agent_id>.session.json
      checkpoints/
        <ts>.json
      logs/
```

---

## 3. Lifecycle states

`created → planning → active → blocked|paused → under_review → completed → archived`

Transitions are explicit Project OS API calls with actor (`user|master|agent`) and reason. Switching projects implies `checkpoint` on the source if `active`.

---

## 4. Registry & metadata

SQLite `projects` columns (illustrative):  
`id, name, slug, state, goal, created_at, updated_at, last_active_at, workspace_path, default_branch, active_agent, risk_flags_json`

`tasks`:  
`id, project_id, title, agent_id, state, parent_id, priority, payload_json, result_json, created_at, updated_at`

`events`: append-only audit (`type, actor, payload, ts`)

`file_locks`: `path, project_id, agent_id, expires_at`

---

## 5. Memory layers

| Layer | Location | Use |
|---|---|---|
| User memory | global + optional Mark sync | Preferences, language |
| Global Pyra memory | global/ | Host capabilities, tool health |
| Project memory | memory.jsonl + DB decisions | Technical continuity |
| Agent memory | agents/*.session.json | Scratch; expendable |
| Execution history | events + logs/ | Forensics |
| Decision records | structured events `decision.*` | Architecture choices |

Semantic search: optional Phase 8+ over artifacts; structured queries always available.

---

## 6. Switching algorithm

On `project_switch(target)`:

1. Assert target exists.  
2. If current:  
   - Request agents to park (timeout).  
   - Snapshot: branch, dirty files hash, open task ids, serial port owners, n8n run ids.  
   - Write checkpoint JSON + DB row.  
   - Set state `paused` if was `active` (policy: keep `active` only one project — **single foreground project**).  
3. Load target context pack.  
4. Restore leases if still valid; else clear.  
5. Return summary for Master speech.

**Foreground model:** one active project for interactive work; background jobs may continue if marked `detachable` (e.g., long cloud run) with resource governor.

---

## 7. Checkpoints & resume

Checkpoint contains: project state, task snapshot, agent session refs, git HEAD, tool evidence ids, pending approvals.

Resume:  
- Prefer ACP `session/resume` when `session_ref` valid.  
- Else create new agent run with `checkpoint_digest` in goal.  
- Project OS remains truth if external session lost.

---

## 8. APIs (Master-facing)

`project_create`, `project_list`, `project_get`, `project_switch`, `project_pause`, `project_note`, `task_add`, `task_update`, `task_list`, `checkpoint_create`, `checkpoint_restore`, `artifact_add`, `decision_add`, `file_lock`, `file_unlock`

CLI `pyra project ...` wraps the same for debugging without Mark.

---

## 9. Unlimited projects

Bounded only by disk. UI/Master lists by `last_active_at`. Archived projects excluded from default routing unless named.
