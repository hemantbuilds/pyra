"""Phase 7 L3 — programming / erase (approval-gated by Broker.invoke)."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..paths import resolve_in_roots
from ..permissions import PermissionLevel
from .registry import ToolRegistry, ToolSpec

if TYPE_CHECKING:
    from ..broker import DeviceBroker


def register(reg: ToolRegistry, broker: "DeviceBroker") -> None:
    reg.register(ToolSpec(
        name="program_firmware",
        description=(
            "Program a firmware artifact to a qualified board (Level 3). "
            "Requires Broker-minted single-use approval bound to artifact hash."
        ),
        level=PermissionLevel.L3,
        category="flash",
        handler=lambda **kw: program_firmware(broker, **kw),
        input_schema={
            "type": "object",
            "properties": {
                "artifact_path": {"type": "string"},
                "artifact_sha256": {"type": "string"},
                "board_id": {"type": "string"},
                "device_identity": {"type": "string"},
                "programmer": {"type": "string"},
                "memory_address": {"type": "string"},
                "erase_required": {"type": "boolean"},
                "approval_id": {"type": "string"},
                "timeout_s": {"type": "number"},
            },
            "required": [
                "artifact_path",
                "artifact_sha256",
                "board_id",
                "device_identity",
                "programmer",
                "memory_address",
            ],
        },
    ))
    reg.register(ToolSpec(
        name="erase_flash",
        description=(
            "Erase flash region on a qualified board (Level 3). "
            "Requires a separate Broker-minted erase approval."
        ),
        level=PermissionLevel.L3,
        category="flash",
        handler=lambda **kw: erase_flash(broker, **kw),
        input_schema={
            "type": "object",
            "properties": {
                "board_id": {"type": "string"},
                "device_identity": {"type": "string"},
                "programmer": {"type": "string"},
                "memory_address": {"type": "string"},
                "artifact_sha256": {"type": "string"},
                "approval_id": {"type": "string"},
                "timeout_s": {"type": "number"},
            },
            "required": [
                "board_id",
                "device_identity",
                "programmer",
                "memory_address",
                "artifact_sha256",
            ],
        },
    ))


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def program_firmware(
    broker: "DeviceBroker",
    *,
    artifact_path: str,
    artifact_sha256: str,
    board_id: str,
    device_identity: str,
    programmer: str,
    memory_address: str,
    erase_required: bool = False,
    approval_id: str | None = None,
    timeout_s: float | None = None,
    **_: Any,
) -> dict[str, Any]:
    roots = broker.approved_roots(write=False)
    path = resolve_in_roots(artifact_path, roots, must_exist=True)
    if not path.is_file():
        raise FileNotFoundError(f"artifact not found: {artifact_path}")
    actual = _hash_file(path)
    expected = (artifact_sha256 or "").strip().lower()
    if actual != expected:
        raise PermissionError(
            f"artifact hash mismatch: expected {expected}, got {actual}"
        )
    if erase_required:
        raise PermissionError(
            "erase_required=true is not permitted on program_firmware; "
            "obtain a separate erase_flash approval first"
        )

    started = time.monotonic()
    runner = getattr(broker, "_program_runner", None)
    if runner is not None:
        result = runner(
            artifact_path=str(path),
            artifact_sha256=actual,
            board_id=board_id,
            device_identity=device_identity,
            programmer=programmer,
            memory_address=memory_address,
            timeout_s=timeout_s or 60.0,
        )
    else:
        # No live programmer backend configured — fail closed (never fake success).
        raise FileNotFoundError(
            f"programmer backend not configured for {programmer!r}; "
            "cannot execute live programming on this host"
        )

    duration_ms = (time.monotonic() - started) * 1000.0
    ok = bool(result.get("success"))
    if not ok:
        raise RuntimeError(result.get("error") or "programming failed")
    return {
        "success": True,
        "artifact_path": str(path),
        "artifact_sha256": actual,
        "board_id": board_id,
        "device_identity": device_identity,
        "programmer": programmer,
        "memory_address": memory_address,
        "approval_id": approval_id,
        "duration_ms": round(duration_ms, 2),
        "backend": result.get("backend", "injected"),
        "stdout": (result.get("stdout") or "")[:4000],
        "stderr": (result.get("stderr") or "")[:4000],
    }


def erase_flash(
    broker: "DeviceBroker",
    *,
    board_id: str,
    device_identity: str,
    programmer: str,
    memory_address: str,
    artifact_sha256: str,
    approval_id: str | None = None,
    timeout_s: float | None = None,
    **_: Any,
) -> dict[str, Any]:
    runner = getattr(broker, "_erase_runner", None)
    if runner is None:
        raise FileNotFoundError(
            f"erase backend not configured for {programmer!r}"
        )
    result = runner(
        board_id=board_id,
        device_identity=device_identity,
        programmer=programmer,
        memory_address=memory_address,
        timeout_s=timeout_s or 60.0,
    )
    if not result.get("success"):
        raise RuntimeError(result.get("error") or "erase failed")
    return {
        "success": True,
        "board_id": board_id,
        "device_identity": device_identity,
        "programmer": programmer,
        "memory_address": memory_address,
        "artifact_sha256": artifact_sha256,
        "approval_id": approval_id,
        "backend": result.get("backend", "injected"),
    }
