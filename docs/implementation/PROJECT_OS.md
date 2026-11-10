# Project OS — Phase 2

**Status:** Complete  
**Runtime root:** `~/PyraWork` (override with `PYRA_WORK_ROOT`)  
**Package:** `agent-os/project_os/`  
**Master wiring:** `master/project_service.py`, `master/project_handlers.py`

---

## Architecture

```text
User / Mark-LIII
      ↓
Dot (/dot/v1/interact)
      ↓
Master orchestrator (deterministic intent → capability)
      ↓
project_os capability
      ↓
ProjectOS manager
      ├── SQLite  ~/PyraWork/pyra.db   (authoritative structured state)
      └── FS      ~/PyraWork/projects/<id>/  (docs, memory mirror, checkpoints, workspace)
```

SQLite is authoritative for project metadata, tasks, memory entries, active-project pointer, and checkpoint metadata. Filesystem trees hold `PROJECT.md`, workspace files, checkpoint snapshot files, and a non-authoritative `state.json` / `memory.jsonl` mirror.

---

## Layout

```text
~/PyraWork/
├── pyra.db
├── global/
└── projects/
    └── <project_id>/
        ├── PROJECT.md
        ├── state.json          # mirror only
        ├── workspace/
        ├── memory/memory.jsonl # append mirror
        ├── tasks/
        ├── artifacts/
        ├── checkpoints/<checkpoint_id>/{manifest,snapshot,PROJECT}.json|md
        ├── logs/
        ├── reports/
        └── agents/
```

---

## Database schema

| Table | Role |
|---|---|
| `meta` | Key/value; `active_project_id` restored across restarts |
| `projects` | Identity, slug, state, goal, description, workspace path, archived |
| `tasks` | Per-project tasks (state, priority, optional parent) |
| `memory_entries` | Notes and engineering decisions scoped by `project_id` |
| `checkpoints` | Metadata + `snapshot_json` + `fs_path` |
| `events` | Append-only audit log |

Foreign keys + WAL. Shared connection uses `check_same_thread=False` with an `RLock` for FastAPI worker threads.

---

## Operations (via Master / Dot NL)

| Intent | Example phrase |
|---|---|
| `project_create` | "Create a new drone development project." |
| `project_list` | "Show my projects." / "List my projects." |
| `project_switch` | "Switch to the hardware bring-up project." |
| `project_continue` | "Continue my drone project." / "What were we working on?" |
| `project_status` | "Project status" |
| `project_note` | "Save a note: …" |
| `project_decision` | "Save this engineering decision: …" |
| `project_archive` | "Archive the project" |
| `task_create` | "Add a task to investigate the SPI driver." |
| `task_list` | "List tasks" |
| `task_update` | "Mark the SPI investigation as completed." |
| `checkpoint_create` | "Create a checkpoint before making changes." |
| `checkpoint_restore` | "Restore the checkpoint" |

Deterministic routing handles clear phrases; Ollama is not required for these ops.

HTTP helpers:

- `GET /v1/projects` — list + active id  
- `GET /v1/projects/active/context` — bounded active context pack  

---

## Isolation

- Every task/memory/checkpoint row is keyed by `project_id`.  
- `find_task_in_project` refuses cross-project task ids.  
- `context_pack(project_id)` returns only that project's open tasks, recent memory, and recent checkpoints — never a dump of all projects.  
- Switching projects pauses the previous project and optionally auto-checkpoints it.

---

## Checkpoints & recovery

A checkpoint captures structured state: project row, all tasks, all memory entries, and the active-project pointer at capture time. Contents are stored in SQLite (`snapshot_json`) and mirrored under `checkpoints/<id>/`.

Restore replaces that project's tasks and memory from the snapshot inside a transaction, then refreshes `PROJECT.md` / `state.json`. Checkpoint history is preserved (restore does not delete checkpoints).

Active project survives process restart via `meta.active_project_id`.

---

## Known Phase-2 limits

- Checkpoint restore does **not** roll back arbitrary workspace file trees (only structured Project OS state).  
- Task dependencies are modeled only via optional `parent_id` (no full DAG scheduler).  
- Archive/restore NL coverage is thinner than create/switch/list.  
- Device Broker / Engineering OS remain stubs (Phase 3+).
