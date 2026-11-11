"""Persist Phase 7 engineering artifacts under Project OS FS (authoritative)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _eng_dir(work_root: Path, project_id: str) -> Path:
    d = Path(work_root) / "projects" / project_id / "artifacts" / "engineering"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_engineering_artifact(
    work_root: Path | str,
    project_id: str,
    kind: str,
    data: dict[str, Any],
    *,
    agent_id: str = "",
    task_id: str = "",
) -> str:
    root = _eng_dir(Path(work_root), project_id)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = root / f"{kind}_{stamp}.json"
    payload = {
        "kind": kind,
        "project_id": project_id,
        "agent_id": agent_id,
        "task_id": task_id,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    # Also write/replace latest pointer
    latest = root / f"{kind}_latest.json"
    latest.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return str(path)


def load_latest_artifact(work_root: Path | str, project_id: str, kind: str) -> Optional[dict[str, Any]]:
    path = Path(work_root) / "projects" / project_id / "artifacts" / "engineering" / f"{kind}_latest.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_engineering_artifacts(work_root: Path | str, project_id: str) -> list[str]:
    root = Path(work_root) / "projects" / project_id / "artifacts" / "engineering"
    if not root.is_dir():
        return []
    return sorted(str(p) for p in root.glob("*.json"))
