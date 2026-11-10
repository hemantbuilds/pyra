"""Project OS manager — create/list/switch/tasks/memory/checkpoints."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

from . import store
from .db import connect, meta_get, meta_set
from .errors import ConflictError, NotFoundError, ProjectOSError, ValidationError
from .ids import new_id, slugify, utc_now

ACTIVE_KEY = "active_project_id"
VALID_PROJECT_STATES = {
    "created", "planning", "active", "blocked", "paused",
    "under_review", "completed", "archived",
}
VALID_TASK_STATES = {"pending", "in_progress", "blocked", "done", "cancelled"}


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


class ProjectOS:
    def __init__(self, work_root: Path | str):
        self.work_root = Path(work_root).expanduser().resolve()
        self.work_root.mkdir(parents=True, exist_ok=True)
        (self.work_root / "projects").mkdir(exist_ok=True)
        (self.work_root / "global").mkdir(exist_ok=True)
        self.db_path = self.work_root / "pyra.db"
        self._lock = threading.RLock()
        self._conn = connect(self.db_path)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ── projects ─────────────────────────────────────────────────────────────

    def create(
        self,
        name: str,
        *,
        goal: str = "",
        description: str = "",
        template: str | None = None,
        actor: str = "master",
        make_active: bool = True,
    ) -> dict[str, Any]:
        name = (name or "").strip()
        if not name:
            raise ValidationError("project name is required")

        base_slug = slugify(name)
        slug = base_slug
        n = 2
        while self._conn.execute(
            "SELECT 1 FROM projects WHERE slug = ?", (slug,)
        ).fetchone():
            slug = f"{base_slug}-{n}"
            n += 1

        project_id = new_id("p_")
        now = utc_now()
        root = store.ensure_project_tree(self.work_root, project_id)
        workspace = str(root / "workspace")
        state = "active" if make_active else "created"

        try:
            with self._conn:
                if make_active:
                    current = meta_get(self._conn, ACTIVE_KEY)
                    if current:
                        self._pause_project_tx(current, actor=actor, reason="switched_on_create")
                self._conn.execute(
                    """
                    INSERT INTO projects(
                        id, name, slug, state, goal, description,
                        created_at, updated_at, last_active_at, workspace_path, archived
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (
                        project_id, name, slug, state, goal or "", description or "",
                        now, now, now if make_active else None, workspace,
                    ),
                )
                if make_active:
                    meta_set(self._conn, ACTIVE_KEY, project_id)
                self._event_tx(
                    project_id, "project.created", actor,
                    {"name": name, "slug": slug, "template": template},
                )
        except Exception:
            # Best-effort cleanup of empty tree if DB insert failed
            raise

        store.write_project_md(root, name=name, goal=goal or "", state=state, project_id=project_id)
        row = self.get(project_id)
        store.write_state_mirror(root, row)
        return row

    def list_projects(self, *, include_archived: bool = False) -> list[dict[str, Any]]:
        if include_archived:
            rows = self._conn.execute(
                "SELECT * FROM projects ORDER BY COALESCE(last_active_at, updated_at) DESC"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM projects WHERE archived = 0 "
                "ORDER BY COALESCE(last_active_at, updated_at) DESC"
            ).fetchall()
        return [_row_to_dict(r) for r in rows]  # type: ignore[misc]

    def get(self, project_id: str) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"project not found: {project_id}")
        return _row_to_dict(row)  # type: ignore[return-value]

    def find_by_ref(self, ref: str) -> dict[str, Any]:
        """Resolve id, slug, or case-insensitive name/substring."""
        ref = (ref or "").strip()
        if not ref:
            raise ValidationError("project reference is empty")

        by_id = self._conn.execute(
            "SELECT * FROM projects WHERE id = ?", (ref,)
        ).fetchone()
        if by_id:
            return _row_to_dict(by_id)  # type: ignore[return-value]

        slug = slugify(ref)
        by_slug = self._conn.execute(
            "SELECT * FROM projects WHERE slug = ?", (slug,)
        ).fetchone()
        if by_slug:
            return _row_to_dict(by_slug)  # type: ignore[return-value]

        rows = self._conn.execute(
            "SELECT * FROM projects WHERE archived = 0 AND lower(name) = lower(?)",
            (ref,),
        ).fetchall()
        if len(rows) == 1:
            return _row_to_dict(rows[0])  # type: ignore[return-value]

        rows = self._conn.execute(
            "SELECT * FROM projects WHERE archived = 0 AND lower(name) LIKE ?",
            (f"%{ref.lower()}%",),
        ).fetchall()
        if len(rows) == 1:
            return _row_to_dict(rows[0])  # type: ignore[return-value]
        if len(rows) > 1:
            names = ", ".join(r["name"] for r in rows)
            raise ConflictError(f"ambiguous project reference '{ref}': {names}")
        raise NotFoundError(f"project not found: {ref}")

    def update(
        self,
        project_id: str,
        *,
        name: str | None = None,
        goal: str | None = None,
        description: str | None = None,
        state: str | None = None,
        actor: str = "master",
    ) -> dict[str, Any]:
        proj = self.get(project_id)
        if state is not None and state not in VALID_PROJECT_STATES:
            raise ValidationError(f"invalid project state: {state}")
        now = utc_now()
        new_name = name if name is not None else proj["name"]
        new_goal = goal if goal is not None else proj["goal"]
        new_desc = description if description is not None else proj["description"]
        new_state = state if state is not None else proj["state"]
        with self._conn:
            self._conn.execute(
                """
                UPDATE projects
                SET name = ?, goal = ?, description = ?, state = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_name, new_goal, new_desc, new_state, now, project_id),
            )
            self._event_tx(project_id, "project.updated", actor, {
                "name": new_name, "goal": new_goal, "state": new_state,
            })
        row = self.get(project_id)
        root = store.project_root(self.work_root, project_id)
        store.write_project_md(
            root, name=row["name"], goal=row["goal"], state=row["state"], project_id=project_id
        )
        store.write_state_mirror(root, row)
        return row

    def archive(self, project_id: str, *, actor: str = "master") -> dict[str, Any]:
        self.get(project_id)
        with self._conn:
            self._conn.execute(
                "UPDATE projects SET archived = 1, state = 'archived', updated_at = ? WHERE id = ?",
                (utc_now(), project_id),
            )
            if meta_get(self._conn, ACTIVE_KEY) == project_id:
                meta_set(self._conn, ACTIVE_KEY, "")
            self._event_tx(project_id, "project.archived", actor, {})
        return self.get(project_id)

    def restore_archived(self, project_id: str, *, actor: str = "master") -> dict[str, Any]:
        self.get(project_id)
        with self._conn:
            self._conn.execute(
                "UPDATE projects SET archived = 0, state = 'paused', updated_at = ? WHERE id = ?",
                (utc_now(), project_id),
            )
            self._event_tx(project_id, "project.restored", actor, {})
        return self.get(project_id)

    def active_id(self) -> str | None:
        val = meta_get(self._conn, ACTIVE_KEY)
        return val or None

    def active_project(self) -> dict[str, Any] | None:
        pid = self.active_id()
        if not pid:
            return None
        try:
            return self.get(pid)
        except NotFoundError:
            return None

    def switch(self, ref: str, *, actor: str = "master", checkpoint: bool = True) -> dict[str, Any]:
        target = self.find_by_ref(ref)
        if target.get("archived"):
            raise ValidationError(f"project is archived: {target['name']}")

        current_id = self.active_id()
        with self._conn:
            if current_id and current_id != target["id"]:
                if checkpoint:
                    self._checkpoint_tx(current_id, label="auto-switch", actor=actor)
                self._pause_project_tx(current_id, actor=actor, reason="switch")
            now = utc_now()
            self._conn.execute(
                """
                UPDATE projects
                SET state = 'active', last_active_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, now, target["id"]),
            )
            meta_set(self._conn, ACTIVE_KEY, target["id"])
            self._event_tx(target["id"], "project.switched", actor, {
                "from": current_id, "to": target["id"],
            })

        row = self.get(target["id"])
        root = store.project_root(self.work_root, row["id"])
        store.write_project_md(
            root, name=row["name"], goal=row["goal"], state=row["state"], project_id=row["id"]
        )
        store.write_state_mirror(root, row)
        return {
            "project": row,
            "context": self.context_pack(row["id"]),
            "previous_project_id": current_id,
        }

    def continue_active(self, ref: str | None = None, *, actor: str = "master") -> dict[str, Any]:
        if ref:
            return self.switch(ref, actor=actor, checkpoint=True)
        active = self.active_project()
        if not active:
            raise NotFoundError("no active project to continue")
        return {
            "project": active,
            "context": self.context_pack(active["id"]),
            "previous_project_id": active["id"],
        }

    def context_pack(self, project_id: str, *, memory_limit: int = 8, task_limit: int = 20) -> dict[str, Any]:
        """Bounded context for Master — never dumps all projects."""
        proj = self.get(project_id)
        tasks = self.list_tasks(project_id)
        open_tasks = [t for t in tasks if t["state"] not in ("done", "cancelled")][:task_limit]
        memory = self.list_memory(project_id, limit=memory_limit)
        checkpoints = self.list_checkpoints(project_id)[:5]
        return {
            "project": {
                "id": proj["id"],
                "name": proj["name"],
                "slug": proj["slug"],
                "state": proj["state"],
                "goal": proj["goal"],
                "description": proj["description"],
            },
            "open_tasks": open_tasks,
            "recent_memory": memory,
            "recent_checkpoints": [
                {"id": c["id"], "label": c["label"], "created_at": c["created_at"]}
                for c in checkpoints
            ],
        }

    # ── tasks ────────────────────────────────────────────────────────────────

    def add_task(
        self,
        project_id: str,
        title: str,
        *,
        description: str = "",
        priority: int = 0,
        parent_id: str | None = None,
        actor: str = "master",
    ) -> dict[str, Any]:
        self.get(project_id)
        title = (title or "").strip()
        if not title:
            raise ValidationError("task title is required")
        task_id = new_id("t_")
        now = utc_now()
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO tasks(
                    id, project_id, title, description, state, priority, parent_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?)
                """,
                (task_id, project_id, title, description or "", priority, parent_id, now, now),
            )
            self._event_tx(project_id, "task.created", actor, {"task_id": task_id, "title": title})
        return self.get_task(task_id)

    def get_task(self, task_id: str) -> dict[str, Any]:
        row = self._conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"task not found: {task_id}")
        return _row_to_dict(row)  # type: ignore[return-value]

    def list_tasks(self, project_id: str) -> list[dict[str, Any]]:
        self.get(project_id)
        rows = self._conn.execute(
            "SELECT * FROM tasks WHERE project_id = ? ORDER BY priority DESC, created_at ASC",
            (project_id,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]  # type: ignore[misc]

    def update_task(
        self,
        task_id: str,
        *,
        state: str | None = None,
        title: str | None = None,
        description: str | None = None,
        priority: int | None = None,
        actor: str = "master",
    ) -> dict[str, Any]:
        task = self.get_task(task_id)
        if state is not None and state not in VALID_TASK_STATES:
            raise ValidationError(f"invalid task state: {state}")
        now = utc_now()
        with self._conn:
            self._conn.execute(
                """
                UPDATE tasks
                SET title = ?, description = ?, state = ?, priority = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    title if title is not None else task["title"],
                    description if description is not None else task["description"],
                    state if state is not None else task["state"],
                    priority if priority is not None else task["priority"],
                    now,
                    task_id,
                ),
            )
            self._event_tx(task["project_id"], "task.updated", actor, {
                "task_id": task_id, "state": state or task["state"],
            })
        return self.get_task(task_id)

    def find_task_in_project(self, project_id: str, ref: str) -> dict[str, Any]:
        ref = (ref or "").strip()
        if not ref:
            raise ValidationError("task reference is empty")
        try:
            task = self.get_task(ref)
            if task["project_id"] != project_id:
                raise NotFoundError(f"task not in project: {ref}")
            return task
        except NotFoundError:
            pass
        rows = self._conn.execute(
            "SELECT * FROM tasks WHERE project_id = ? AND lower(title) LIKE ?",
            (project_id, f"%{ref.lower()}%"),
        ).fetchall()
        if len(rows) == 1:
            return _row_to_dict(rows[0])  # type: ignore[return-value]
        if len(rows) > 1:
            raise ConflictError(f"ambiguous task reference '{ref}'")
        raise NotFoundError(f"task not found: {ref}")

    # ── memory ───────────────────────────────────────────────────────────────

    def add_memory(
        self,
        project_id: str,
        text: str,
        *,
        kind: str = "note",
        actor: str = "master",
    ) -> dict[str, Any]:
        self.get(project_id)
        text = (text or "").strip()
        if not text:
            raise ValidationError("memory text is required")
        if kind not in ("note", "decision"):
            raise ValidationError("kind must be note or decision")
        entry_id = new_id("m_")
        now = utc_now()
        entry = {
            "id": entry_id,
            "project_id": project_id,
            "kind": kind,
            "text": text,
            "created_at": now,
        }
        with self._conn:
            self._conn.execute(
                "INSERT INTO memory_entries(id, project_id, kind, text, created_at) VALUES (?, ?, ?, ?, ?)",
                (entry_id, project_id, kind, text, now),
            )
            self._event_tx(project_id, f"memory.{kind}", actor, {"id": entry_id})
        root = store.ensure_project_tree(self.work_root, project_id)
        store.append_memory_jsonl(root, entry)
        return entry

    def list_memory(self, project_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        self.get(project_id)
        rows = self._conn.execute(
            """
            SELECT * FROM memory_entries
            WHERE project_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (project_id, limit),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]  # type: ignore[misc]

    # ── checkpoints ──────────────────────────────────────────────────────────

    def checkpoint(
        self,
        project_id: str,
        *,
        label: str = "",
        actor: str = "master",
    ) -> dict[str, Any]:
        return self._checkpoint_public(project_id, label=label, actor=actor)

    def list_checkpoints(self, project_id: str) -> list[dict[str, Any]]:
        self.get(project_id)
        rows = self._conn.execute(
            """
            SELECT id, project_id, label, created_at, fs_path
            FROM checkpoints WHERE project_id = ?
            ORDER BY created_at DESC
            """,
            (project_id,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]  # type: ignore[misc]

    def get_checkpoint(self, checkpoint_id: str) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT * FROM checkpoints WHERE id = ?", (checkpoint_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"checkpoint not found: {checkpoint_id}")
        data = _row_to_dict(row)
        assert data is not None
        data["snapshot"] = json.loads(data.pop("snapshot_json"))
        return data

    def restore_checkpoint(
        self,
        checkpoint_id: str,
        *,
        actor: str = "master",
    ) -> dict[str, Any]:
        cp = self.get_checkpoint(checkpoint_id)
        project_id = cp["project_id"]
        snap = cp["snapshot"]
        proj_snap = snap.get("project") or {}
        tasks_snap = snap.get("tasks") or []
        memory_snap = snap.get("memory") or []

        with self._conn:
            # Replace mutable project fields from snapshot
            self._conn.execute(
                """
                UPDATE projects
                SET name = ?, goal = ?, description = ?, state = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    proj_snap.get("name", ""),
                    proj_snap.get("goal", ""),
                    proj_snap.get("description", ""),
                    proj_snap.get("state", "paused"),
                    utc_now(),
                    project_id,
                ),
            )
            # Replace tasks for this project
            self._conn.execute("DELETE FROM tasks WHERE project_id = ?", (project_id,))
            for t in tasks_snap:
                self._conn.execute(
                    """
                    INSERT INTO tasks(
                        id, project_id, title, description, state, priority, parent_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        t["id"], project_id, t["title"], t.get("description", ""),
                        t.get("state", "pending"), t.get("priority", 0), t.get("parent_id"),
                        t.get("created_at", utc_now()), t.get("updated_at", utc_now()),
                    ),
                )
            self._conn.execute("DELETE FROM memory_entries WHERE project_id = ?", (project_id,))
            for m in memory_snap:
                self._conn.execute(
                    "INSERT INTO memory_entries(id, project_id, kind, text, created_at) VALUES (?, ?, ?, ?, ?)",
                    (m["id"], project_id, m["kind"], m["text"], m["created_at"]),
                )
            self._event_tx(project_id, "checkpoint.restored", actor, {
                "checkpoint_id": checkpoint_id,
            })

        row = self.get(project_id)
        root = store.ensure_project_tree(self.work_root, project_id)
        store.write_project_md(
            root, name=row["name"], goal=row["goal"], state=row["state"], project_id=project_id
        )
        store.write_state_mirror(root, row)
        return {"project": row, "checkpoint_id": checkpoint_id, "context": self.context_pack(project_id)}

    # ── internals ────────────────────────────────────────────────────────────

    def _pause_project_tx(self, project_id: str, *, actor: str, reason: str) -> None:
        self._conn.execute(
            "UPDATE projects SET state = 'paused', updated_at = ? WHERE id = ? AND archived = 0",
            (utc_now(), project_id),
        )
        self._event_tx(project_id, "project.paused", actor, {"reason": reason})

    def _checkpoint_public(self, project_id: str, *, label: str, actor: str) -> dict[str, Any]:
        with self._conn:
            return self._checkpoint_tx(project_id, label=label, actor=actor)

    def _checkpoint_tx(self, project_id: str, *, label: str, actor: str) -> dict[str, Any]:
        proj = _row_to_dict(
            self._conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        )
        if proj is None:
            raise NotFoundError(f"project not found: {project_id}")
        tasks = [
            _row_to_dict(r)
            for r in self._conn.execute(
                "SELECT * FROM tasks WHERE project_id = ?", (project_id,)
            ).fetchall()
        ]
        memory = [
            _row_to_dict(r)
            for r in self._conn.execute(
                "SELECT * FROM memory_entries WHERE project_id = ?", (project_id,)
            ).fetchall()
        ]
        snapshot = {
            "project": proj,
            "tasks": tasks,
            "memory": memory,
            "active_project_id": meta_get(self._conn, ACTIVE_KEY),
        }
        checkpoint_id = new_id("c_")
        now = utc_now()
        root = store.ensure_project_tree(self.work_root, project_id)
        cp_dir = store.write_checkpoint_files(root, checkpoint_id, snapshot)
        self._conn.execute(
            """
            INSERT INTO checkpoints(id, project_id, label, created_at, snapshot_json, fs_path)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                checkpoint_id, project_id, label or "", now,
                json.dumps(snapshot, ensure_ascii=False), str(cp_dir),
            ),
        )
        self._event_tx(project_id, "checkpoint.created", actor, {
            "checkpoint_id": checkpoint_id, "label": label,
        })
        return {
            "id": checkpoint_id,
            "project_id": project_id,
            "label": label or "",
            "created_at": now,
            "fs_path": str(cp_dir),
        }

    def _event_tx(self, project_id: str | None, type_: str, actor: str, payload: dict) -> None:
        self._conn.execute(
            "INSERT INTO events(project_id, type, actor, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (project_id, type_, actor, json.dumps(payload, ensure_ascii=False), utc_now()),
        )


# Re-export error name expected by package __init__
__all__ = ["ProjectOS", "ProjectOSError"]
