"""Filesystem tools with path jail."""

from __future__ import annotations

import shutil
import stat
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..paths import PathJailError, resolve_in_roots
from ..permissions import PermissionLevel
from .registry import ToolRegistry, ToolSpec

if TYPE_CHECKING:
    from ..broker import DeviceBroker


def register(reg: ToolRegistry, broker: "DeviceBroker") -> None:
    reg.register(ToolSpec(
        name="list_directory",
        description="List entries in an approved directory (Level 0).",
        level=PermissionLevel.L0,
        category="fs",
        handler=lambda **kw: list_directory(broker, **kw),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path (relative to workspace or absolute under roots)"},
            },
            "required": ["path"],
        },
    ))
    reg.register(ToolSpec(
        name="get_file_info",
        description="Stat a file or directory inside approved roots (Level 0).",
        level=PermissionLevel.L0,
        category="fs",
        handler=lambda **kw: get_file_info(broker, **kw),
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    ))
    reg.register(ToolSpec(
        name="read_text_file",
        description="Read a text file inside approved roots (Level 0).",
        level=PermissionLevel.L0,
        category="fs",
        handler=lambda **kw: read_text_file(broker, **kw),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "max_bytes": {"type": "integer"},
            },
            "required": ["path"],
        },
    ))
    reg.register(ToolSpec(
        name="create_directory",
        description="Create a directory inside the approved workspace (Level 1).",
        level=PermissionLevel.L1,
        category="fs",
        handler=lambda **kw: create_directory(broker, **kw),
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    ))
    reg.register(ToolSpec(
        name="write_text_file",
        description="Write/create a text file inside the approved workspace (Level 1).",
        level=PermissionLevel.L1,
        category="fs",
        handler=lambda **kw: write_text_file(broker, **kw),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "overwrite": {"type": "boolean"},
            },
            "required": ["path", "content"],
        },
    ))
    reg.register(ToolSpec(
        name="copy_file",
        description="Copy a file within approved roots (Level 1).",
        level=PermissionLevel.L1,
        category="fs",
        handler=lambda **kw: copy_file(broker, **kw),
        input_schema={
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "destination": {"type": "string"},
            },
            "required": ["source", "destination"],
        },
    ))


def list_directory(broker: "DeviceBroker", *, path: str, **_: Any) -> dict[str, Any]:
    roots = broker.approved_roots(write=False)
    target = resolve_in_roots(path, roots, must_exist=True)
    if not target.is_dir():
        raise PathJailError(f"not a directory: {path}")
    entries = []
    for i, child in enumerate(sorted(target.iterdir(), key=lambda p: p.name)):
        if i >= broker.policy.max_list_entries:
            break
        try:
            st = child.lstat()
            entries.append({
                "name": child.name,
                "path": str(child),
                "is_dir": child.is_dir(),
                "is_symlink": child.is_symlink(),
                "size": st.st_size,
            })
        except OSError:
            entries.append({"name": child.name, "path": str(child), "error": "stat_failed"})
    return {"path": str(target), "entries": entries, "count": len(entries)}


def get_file_info(broker: "DeviceBroker", *, path: str, **_: Any) -> dict[str, Any]:
    roots = broker.approved_roots(write=False)
    target = resolve_in_roots(path, roots, must_exist=True)
    st = target.lstat()
    return {
        "path": str(target),
        "exists": True,
        "is_dir": stat.S_ISDIR(st.st_mode),
        "is_file": stat.S_ISREG(st.st_mode),
        "is_symlink": stat.S_ISLNK(st.st_mode),
        "size": st.st_size,
        "mode": oct(st.st_mode & 0o777),
        "mtime": st.st_mtime,
    }


def read_text_file(
    broker: "DeviceBroker",
    *,
    path: str,
    max_bytes: int | None = None,
    **_: Any,
) -> dict[str, Any]:
    roots = broker.approved_roots(write=False)
    target = resolve_in_roots(path, roots, must_exist=True)
    if not target.is_file():
        raise PathJailError(f"not a file: {path}")
    limit = min(max_bytes or broker.policy.max_read_bytes, broker.policy.max_read_bytes)
    data = target.read_bytes()
    truncated = len(data) > limit
    data = data[:limit]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("utf-8", errors="replace")
    return {
        "path": str(target),
        "content": text,
        "bytes_read": len(data),
        "truncated": truncated,
    }


def create_directory(broker: "DeviceBroker", *, path: str, **_: Any) -> dict[str, Any]:
    roots = broker.approved_roots(write=True)
    target = resolve_in_roots(path, roots, for_write=True)
    target.mkdir(parents=True, exist_ok=True)
    return {"path": str(target), "created": True}


def write_text_file(
    broker: "DeviceBroker",
    *,
    path: str,
    content: str,
    overwrite: bool = True,
    **_: Any,
) -> dict[str, Any]:
    roots = broker.approved_roots(write=True)
    target = resolve_in_roots(path, roots, for_write=True)
    raw = (content or "").encode("utf-8")
    if len(raw) > broker.policy.max_write_bytes:
        raise ValueError(f"content exceeds max_write_bytes ({broker.policy.max_write_bytes})")
    if target.exists() and not overwrite:
        raise FileExistsError(f"file exists: {path}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    return {"path": str(target), "bytes_written": len(raw)}


def copy_file(
    broker: "DeviceBroker",
    *,
    source: str,
    destination: str,
    **_: Any,
) -> dict[str, Any]:
    read_roots = broker.approved_roots(write=False)
    write_roots = broker.approved_roots(write=True)
    src = resolve_in_roots(source, read_roots, must_exist=True)
    dst = resolve_in_roots(destination, write_roots, for_write=True)
    if not src.is_file():
        raise PathJailError(f"source is not a file: {source}")
    if src.stat().st_size > broker.policy.max_read_bytes:
        raise ValueError("source file too large to copy under policy limits")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return {"source": str(src), "destination": str(dst)}
