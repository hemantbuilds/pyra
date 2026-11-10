"""Append-only Device Broker audit log (SQLite)."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .redaction import redact_value
from .types import AuditStatus

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
    id              TEXT PRIMARY KEY,
    operation_id    TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    status          TEXT NOT NULL,
    principal       TEXT NOT NULL,
    client          TEXT NOT NULL,
    project_id      TEXT,
    tool            TEXT NOT NULL,
    level           TEXT NOT NULL,
    args_json       TEXT NOT NULL,
    result_json     TEXT,
    error           TEXT,
    approval_id     TEXT,
    duration_ms     REAL
);
CREATE INDEX IF NOT EXISTS idx_audit_op ON audit_events(operation_id);
CREATE INDEX IF NOT EXISTS idx_audit_project ON audit_events(project_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_events(created_at);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_operation_id() -> str:
    return "op_" + uuid.uuid4().hex[:12]


class AuditLog:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            str(self.db_path), timeout=30, check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def record(
        self,
        *,
        operation_id: str,
        status: AuditStatus | str,
        principal: str,
        client: str,
        tool: str,
        level: str,
        args: dict[str, Any],
        project_id: Optional[str] = None,
        result: Optional[dict[str, Any]] = None,
        error: Optional[str] = None,
        approval_id: Optional[str] = None,
        duration_ms: Optional[float] = None,
    ) -> str:
        event_id = "ae_" + uuid.uuid4().hex[:12]
        status_v = status.value if isinstance(status, AuditStatus) else str(status)
        safe_args = redact_value(args)
        safe_result = redact_value(result) if result is not None else None
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO audit_events(
                    id, operation_id, created_at, status, principal, client,
                    project_id, tool, level, args_json, result_json, error,
                    approval_id, duration_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    operation_id,
                    _utc_now(),
                    status_v,
                    principal,
                    client,
                    project_id,
                    tool,
                    level,
                    json.dumps(safe_args, ensure_ascii=False),
                    None if safe_result is None else json.dumps(safe_result, ensure_ascii=False),
                    error,
                    approval_id,
                    duration_ms,
                ),
            )
            self._conn.commit()
        return event_id

    def recent(
        self,
        *,
        limit: int = 50,
        project_id: Optional[str] = None,
        tool: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        q = "SELECT * FROM audit_events"
        clauses: list[str] = []
        params: list[Any] = []
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        if tool:
            clauses.append("tool = ?")
            params.append(tool)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(q, params).fetchall()
        out = []
        for r in rows:
            out.append({k: r[k] for k in r.keys()})
        return out
