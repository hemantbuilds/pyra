"""Filesystem layout under ~/PyraWork/projects/<id>/."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

PROJECT_DIRS = (
    "workspace",
    "memory",
    "tasks",
    "artifacts",
    "checkpoints",
    "logs",
    "reports",
    "agents",
)


def project_root(work_root: Path, project_id: str) -> Path:
    return work_root / "projects" / project_id


def ensure_project_tree(work_root: Path, project_id: str) -> Path:
    root = project_root(work_root, project_id)
    root.mkdir(parents=True, exist_ok=True)
    for name in PROJECT_DIRS:
        (root / name).mkdir(exist_ok=True)
    return root


def write_project_md(root: Path, *, name: str, goal: str, state: str, project_id: str) -> None:
    content = (
        f"# {name}\n\n"
        f"- **id:** `{project_id}`\n"
        f"- **state:** {state}\n"
        f"- **goal:** {goal or '(none)'}\n"
    )
    (root / "PROJECT.md").write_text(content, encoding="utf-8")


def write_state_mirror(root: Path, row: dict) -> None:
    """Non-authoritative human-readable mirror of the DB row."""
    (root / "state.json").write_text(
        json.dumps(row, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def append_memory_jsonl(root: Path, entry: dict) -> None:
    path = root / "memory" / "memory.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def write_checkpoint_files(root: Path, checkpoint_id: str, snapshot: dict) -> Path:
    cp_dir = root / "checkpoints" / checkpoint_id
    if cp_dir.exists():
        shutil.rmtree(cp_dir)
    cp_dir.mkdir(parents=True)
    manifest = {
        "checkpoint_id": checkpoint_id,
        "captured": list(snapshot.keys()),
        "note": "SQLite remains authoritative; this folder stores the captured snapshot.",
    }
    (cp_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    (cp_dir / "snapshot.json").write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    # Preserve PROJECT.md content inside the checkpoint if present
    proj_md = root / "PROJECT.md"
    if proj_md.exists():
        (cp_dir / "PROJECT.md").write_text(proj_md.read_text(encoding="utf-8"), encoding="utf-8")
    return cp_dir
