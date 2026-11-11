"""Phase 6 L2 — deterministic west build (no shell, no flash)."""

from __future__ import annotations

import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..paths import PathJailError, resolve_in_roots
from ..permissions import PermissionLevel
from .registry import ToolRegistry, ToolSpec

if TYPE_CHECKING:
    from ..broker import DeviceBroker

# Zephyr board targets may include @ revision and / SoC path segments.
# Still reject shell metacharacters and path traversal.
_BOARD_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_@/\-.]{0,95}$")


def register(reg: ToolRegistry, broker: "DeviceBroker") -> None:
    reg.register(ToolSpec(
        name="west_build",
        description=(
            "Run a constrained `west build -b <board> <sourcedir>` inside the "
            "project workspace (Level 2). No shell. Never flashes."
        ),
        level=PermissionLevel.L2,
        category="build",
        handler=lambda **kw: west_build(broker, **kw),
        input_schema={
            "type": "object",
            "properties": {
                "board": {"type": "string", "description": "Validated Zephyr board target"},
                "source_dir": {
                    "type": "string",
                    "description": "Firmware source directory under approved roots",
                },
                "build_dir": {
                    "type": "string",
                    "description": "Optional build directory (default: source_dir/build)",
                },
                "extra_args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional extra west args after -- (bounded)",
                },
                "timeout_s": {"type": "number"},
            },
            "required": ["board", "source_dir"],
        },
    ))


def _validate_token(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    if any(ch in value for ch in ("|", ";", "&", "`", "$", "\n", ">", "<")):
        raise PermissionError(f"invalid characters in {field}")
    if ".." in value or value.startswith("-"):
        # board may start with letter only via _BOARD_RE; paths handled by jail
        if field == "board":
            raise PermissionError(f"invalid {field}")
    return value


def west_build(
    broker: "DeviceBroker",
    *,
    board: str,
    source_dir: str,
    build_dir: str | None = None,
    extra_args: list[str] | None = None,
    timeout_s: float | None = None,
    **_: Any,
) -> dict[str, Any]:
    board = _validate_token(board, field="board")
    if ".." in board or not _BOARD_RE.match(board):
        raise PermissionError(f"invalid board target: {board!r}")

    roots = broker.approved_roots(write=False)
    write_roots = broker.approved_roots(write=True)
    src = resolve_in_roots(source_dir, roots, must_exist=True)
    if not src.is_dir():
        raise PathJailError(f"source_dir is not a directory: {source_dir}")

    if build_dir:
        bdir = resolve_in_roots(build_dir, write_roots, must_exist=False)
    else:
        bdir = src / "build"
        # Ensure build path stays under write roots
        resolve_in_roots(str(bdir), write_roots, must_exist=False)

    extras: list[str] = []
    for a in (extra_args or [])[:8]:
        if not isinstance(a, str):
            raise ValueError("extra_args must be strings")
        if any(ch in a for ch in ("|", ";", "&", "`", "$", "\n", ">", "<")):
            raise PermissionError("invalid characters in extra_args")
        if a.startswith("-c") or a in ("-c", "--command"):
            raise PermissionError("shell-style extra args denied")
        extras.append(a)

    timeout = float(timeout_s if timeout_s is not None else broker.policy.build_timeout_s)
    if timeout <= 0 or timeout > 600:
        raise ValueError("timeout_s out of allowed range (0, 600]")

    argv = ["west", "build", "-b", board, str(src), "--build-dir", str(bdir), *extras]
    started_at = datetime.now(timezone.utc).isoformat()
    t0 = time.monotonic()

    env_allow = {
        "PATH": None,  # filled from os.environ below
        "HOME": None,
        "USER": None,
        "LANG": None,
        "LC_ALL": None,
        "ZEPHYR_BASE": None,
        "ZEPHYR_SDK_INSTALL_DIR": None,
        "ZEPHYR_TOOLCHAIN_VARIANT": None,
        "WEST_PYTHON": None,
    }
    import os

    controlled_env = {k: os.environ[k] for k in env_allow if k in os.environ}

    out_limit = broker.policy.max_build_output_bytes
    lock = broker.workspace_build_lock(str(src.resolve()))
    with lock:
        if broker._build_runner is not None:
            result = broker._build_runner(argv, src, timeout, controlled_env)
        else:
            result = _default_west_runner(
                argv,
                cwd=src,
                timeout=timeout,
                env=controlled_env,
                max_output_bytes=out_limit,
            )

    duration_s = round(time.monotonic() - t0, 3)
    ended_at = datetime.now(timezone.utc).isoformat()
    exit_code = int(result.get("exit_code", 1))
    stdout = str(result.get("stdout") or "")[:out_limit]
    stderr = str(result.get("stderr") or "")[:out_limit]
    success = exit_code == 0 and not result.get("timed_out")

    artifacts: list[str] = []
    for candidate in (
        bdir / "zephyr" / "zephyr.elf",
        bdir / "zephyr" / "zephyr.bin",
        bdir / "zephyr" / "zephyr.hex",
    ):
        if candidate.exists():
            artifacts.append(str(candidate))

    return {
        "success": success,
        "exit_code": exit_code,
        "timed_out": bool(result.get("timed_out")),
        "board": board,
        "source_dir": str(src),
        "build_dir": str(bdir),
        "argv": argv,
        "resolved_executable": result.get("resolved_executable"),
        "cwd": str(src),
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_s": duration_s,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_truncated": bool(result.get("stdout_truncated"))
        or len(str(result.get("stdout") or "")) > out_limit,
        "stderr_truncated": bool(result.get("stderr_truncated"))
        or len(str(result.get("stderr") or "")) > out_limit,
        "artifacts": artifacts,
        "flash_attempted": False,
        "level": "L2",
        "env_keys": sorted(controlled_env.keys()),
        "termination": result.get("termination"),
        "pgid": result.get("pgid"),
    }


def _default_west_runner(
    argv: list[str],
    *,
    cwd: Path,
    timeout: float,
    env: dict[str, str],
    max_output_bytes: int,
) -> dict[str, Any]:
    from ..process_exec import run_process_group

    exe = shutil.which(argv[0])
    if not exe:
        raise FileNotFoundError("west executable not found on PATH")
    final = [exe, *argv[1:]]
    result = run_process_group(
        final,
        cwd=cwd,
        env=env,
        timeout_s=timeout,
        max_output_bytes=max_output_bytes,
    )
    result["resolved_executable"] = exe
    if result.get("timed_out"):
        result["stderr"] = (result.get("stderr") or "") + f"\ntimeout after {timeout}s"
    return result
