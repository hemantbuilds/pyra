"""Phase 6 L2 — bounded passive serial capture (no TX, no config persist)."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from ..permissions import PermissionLevel
from .registry import ToolRegistry, ToolSpec

if TYPE_CHECKING:
    from ..broker import DeviceBroker

_ALLOWED_BAUD = {9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600}
_SERIAL_PREFIXES = ("/dev/ttyACM", "/dev/ttyUSB", "/dev/ttyAMA", "/dev/serial/by-id/")


def register(reg: ToolRegistry, broker: "DeviceBroker") -> None:
    reg.register(ToolSpec(
        name="serial_capture_passive",
        description=(
            "Open a validated serial device for bounded passive capture (Level 2). "
            "No transmission. No persistent configuration."
        ),
        level=PermissionLevel.L2,
        category="serial",
        handler=lambda **kw: serial_capture_passive(broker, **kw),
        input_schema={
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "baudrate": {"type": "integer"},
                "duration_s": {"type": "number"},
                "max_bytes": {"type": "integer"},
                "bytesize": {"type": "integer"},
                "parity": {"type": "string"},
                "stopbits": {"type": "number"},
            },
            "required": ["device"],
        },
    ))
    # Explicit L3 names stay unregistered — invoke denies them.
    # UART TX is intentionally not registered in Phase 6.


def _validate_device_path(device: str) -> str:
    if not isinstance(device, str) or not device.startswith("/dev/"):
        raise PermissionError("serial device must be an absolute /dev path")
    if any(ch in device for ch in ("|", ";", "&", "`", "$", "\n", ">", "<", " ")):
        raise PermissionError("invalid characters in device path")
    if ".." in device:
        raise PermissionError("path traversal denied for serial device")
    if not any(device.startswith(p) for p in _SERIAL_PREFIXES):
        raise PermissionError(f"serial device not in allowlisted prefix: {device}")
    # Resolve by-id links lexically under /dev
    path = Path(device)
    if path.is_symlink():
        target = path.resolve()
        if not str(target).startswith("/dev/"):
            raise PermissionError("serial symlink escape denied")
    return device


def serial_capture_passive(
    broker: "DeviceBroker",
    *,
    device: str,
    baudrate: int = 115200,
    duration_s: float | None = None,
    max_bytes: int | None = None,
    bytesize: int = 8,
    parity: str = "N",
    stopbits: float = 1,
    **_: Any,
) -> dict[str, Any]:
    device = _validate_device_path(device)
    try:
        baud = int(baudrate)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid baudrate") from exc
    if baud not in _ALLOWED_BAUD:
        raise ValueError(f"baudrate not allowed: {baud}")

    if bytesize not in (5, 6, 7, 8):
        raise ValueError("invalid bytesize")
    parity_u = str(parity).upper()
    if parity_u not in ("N", "E", "O", "M", "S"):
        raise ValueError("invalid parity")
    try:
        stop = float(stopbits)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid stopbits") from exc
    if stop not in (1, 1.5, 2):
        raise ValueError("invalid stopbits")

    duration = float(
        duration_s if duration_s is not None else broker.policy.serial_capture_timeout_s
    )
    if duration <= 0 or duration > 30:
        raise ValueError("duration_s out of range (0, 30]")
    limit = int(max_bytes if max_bytes is not None else broker.policy.max_serial_capture_bytes)
    if limit <= 0 or limit > 64_000:
        raise ValueError("max_bytes out of range")

    started_at = datetime.now(timezone.utc).isoformat()
    t0 = time.monotonic()
    settings = {
        "device": device,
        "baudrate": baud,
        "bytesize": bytesize,
        "parity": parity_u,
        "stopbits": stop,
        "duration_s": duration,
        "max_bytes": limit,
    }

    if broker._serial_backend is not None:
        raw = broker._serial_backend(**settings)
    else:
        raw = _default_serial_capture(**settings)

    elapsed = round(time.monotonic() - t0, 3)
    data = bytes(raw.get("data") or b"")[:limit]
    return {
        "success": bool(raw.get("success", True)),
        "device": device,
        "settings": settings,
        "started_at": started_at,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "duration_s": elapsed,
        "bytes_captured": len(data),
        "data_hex": data.hex(),
        "data_text": data.decode("utf-8", errors="replace"),
        "truncated": bool(raw.get("truncated")) or len(bytes(raw.get("data") or b"")) > limit,
        "error": raw.get("error"),
        "tx_attempted": False,
        "flash_attempted": False,
        "level": "L2",
    }


def _default_serial_capture(
    *,
    device: str,
    baudrate: int,
    bytesize: int,
    parity: str,
    stopbits: float,
    duration_s: float,
    max_bytes: int,
) -> dict[str, Any]:
    """Best-effort pyserial capture; fails cleanly if unavailable."""
    try:
        import serial  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise FileNotFoundError(
            "pyserial not available; serial capture requires pyserial or a test backend"
        ) from exc

    parity_map = {
        "N": serial.PARITY_NONE,
        "E": serial.PARITY_EVEN,
        "O": serial.PARITY_ODD,
        "M": serial.PARITY_MARK,
        "S": serial.PARITY_SPACE,
    }
    stop_map = {
        1: serial.STOPBITS_ONE,
        1.5: serial.STOPBITS_ONE_POINT_FIVE,
        2: serial.STOPBITS_TWO,
    }
    buf = bytearray()
    err = None
    try:
        with serial.Serial(
            port=device,
            baudrate=baudrate,
            bytesize=bytesize,
            parity=parity_map[parity],
            stopbits=stop_map[stopbits],
            timeout=0.2,
        ) as ser:
            deadline = time.monotonic() + duration_s
            while time.monotonic() < deadline and len(buf) < max_bytes:
                chunk = ser.read(min(1024, max_bytes - len(buf)))
                if chunk:
                    buf.extend(chunk)
    except Exception as exc:  # noqa: BLE001
        err = f"{type(exc).__name__}: {exc}"
        return {"success": False, "data": bytes(buf), "error": err, "truncated": False}

    return {
        "success": True,
        "data": bytes(buf),
        "truncated": len(buf) >= max_bytes,
        "error": None,
    }
