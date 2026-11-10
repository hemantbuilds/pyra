"""Read-only system / toolchain information tools."""

from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..permissions import PermissionLevel
from .registry import ToolRegistry, ToolSpec

if TYPE_CHECKING:
    from ..broker import DeviceBroker

_TOOLCHAIN_NAMES = (
    "gcc",
    "g++",
    "clang",
    "cmake",
    "ninja",
    "make",
    "git",
    "python3",
    "arm-none-eabi-gcc",
    "avr-gcc",
    "esptool.py",
    "probe-rs",
    "openocd",
    "west",
    "pio",
)


def register(reg: ToolRegistry, broker: "DeviceBroker") -> None:
    reg.register(ToolSpec(
        name="get_system_info",
        description="Host system summary (Level 0).",
        level=PermissionLevel.L0,
        category="sysinfo",
        handler=lambda **kw: get_system_info(broker, **kw),
        input_schema={"type": "object", "properties": {}},
    ))
    reg.register(ToolSpec(
        name="get_platform_info",
        description="Python/platform details (Level 0).",
        level=PermissionLevel.L0,
        category="sysinfo",
        handler=lambda **kw: get_platform_info(broker, **kw),
        input_schema={"type": "object", "properties": {}},
    ))
    reg.register(ToolSpec(
        name="get_available_toolchains",
        description="Locate common embedded/host toolchains on PATH (Level 0).",
        level=PermissionLevel.L0,
        category="sysinfo",
        handler=lambda **kw: get_available_toolchains(broker, **kw),
        input_schema={"type": "object", "properties": {}},
    ))
    reg.register(ToolSpec(
        name="get_installed_tool_versions",
        description="Run allowlisted version probes for installed tools (Level 0).",
        level=PermissionLevel.L0,
        category="sysinfo",
        handler=lambda **kw: get_installed_tool_versions(broker, **kw),
        input_schema={"type": "object", "properties": {}},
    ))
    reg.register(ToolSpec(
        name="list_broker_tools",
        description="List Device Broker tools and permission levels (Level 0).",
        level=PermissionLevel.L0,
        category="meta",
        handler=lambda **kw: list_broker_tools(broker, **kw),
        input_schema={"type": "object", "properties": {}},
    ))
    reg.register(ToolSpec(
        name="get_execution_history",
        description="Retrieve recent Device Broker audit events (Level 0).",
        level=PermissionLevel.L0,
        category="meta",
        handler=lambda **kw: get_execution_history(broker, **kw),
        input_schema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer"},
                "project_id": {"type": "string"},
            },
        },
    ))
    reg.register(ToolSpec(
        name="list_connected_devices_readonly",
        description="Enumerate USB serial-like device nodes read-only (Level 0). No I/O opened.",
        level=PermissionLevel.L0,
        category="sysinfo",
        handler=lambda **kw: list_connected_devices_readonly(broker, **kw),
        input_schema={"type": "object", "properties": {}},
    ))


def get_system_info(broker: "DeviceBroker", **_: Any) -> dict[str, Any]:
    uname = platform.uname()
    return {
        "system": uname.system,
        "node": uname.node,
        "release": uname.release,
        "version": uname.version,
        "machine": uname.machine,
        "processor": uname.processor,
        "work_root": str(broker.policy.work_root),
        "cwd": os.getcwd(),
    }


def get_platform_info(broker: "DeviceBroker", **_: Any) -> dict[str, Any]:
    return {
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "architecture": platform.architecture(),
        "pid": os.getpid(),
    }


def get_available_toolchains(broker: "DeviceBroker", **_: Any) -> dict[str, Any]:
    found = []
    missing = []
    for name in _TOOLCHAIN_NAMES:
        path = shutil.which(name)
        if path:
            found.append({"name": name, "path": path})
        else:
            missing.append(name)
    return {"found": found, "missing": missing}


def get_installed_tool_versions(broker: "DeviceBroker", **_: Any) -> dict[str, Any]:
    """Use Broker's allowlisted runner for version probes only."""
    probes = [
        ["python3", "--version"],
        ["git", "--version"],
        ["cmake", "--version"],
        ["gcc", "--version"],
        ["arm-none-eabi-gcc", "--version"],
        ["esptool.py", "version"],
        ["probe-rs", "--version"],
        ["openocd", "--version"],
        ["uname", "-a"],
    ]
    results = []
    for argv in probes:
        if shutil.which(argv[0]) is None:
            results.append({"argv": argv, "available": False})
            continue
        # Call internal exec without elevating — L0 version commands
        try:
            data = broker._run_command_impl(argv, cwd=None, level_override="L0")  # noqa: SLF001
            results.append({"argv": argv, "available": True, **data})
        except Exception as exc:  # noqa: BLE001
            results.append({"argv": argv, "available": True, "error": str(exc)})
    return {"probes": results}


def list_broker_tools(broker: "DeviceBroker", **_: Any) -> dict[str, Any]:
    tools = [
        {
            "name": t.name,
            "description": t.description,
            "level": t.level.label(),
            "category": t.category,
        }
        for t in broker.registry.list_tools()
    ]
    return {"tools": tools, "count": len(tools)}


def get_execution_history(
    broker: "DeviceBroker",
    *,
    limit: int = 20,
    project_id: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    limit = max(1, min(int(limit or 20), 100))
    pid = project_id or broker.current_project_id()
    rows = broker.audit.recent(limit=limit, project_id=pid)
    return {"events": rows, "count": len(rows), "project_id": pid}


def list_connected_devices_readonly(broker: "DeviceBroker", **_: Any) -> dict[str, Any]:
    """List /dev/ttyACM* /dev/ttyUSB* /dev/serial/by-id without opening them."""
    patterns = [
        Path("/dev").glob("ttyACM*"),
        Path("/dev").glob("ttyUSB*"),
        Path("/dev/serial/by-id").glob("*") if Path("/dev/serial/by-id").exists() else iter(()),
    ]
    devices = []
    for group in patterns:
        for p in group:
            devices.append({
                "path": str(p),
                "is_symlink": p.is_symlink(),
                "resolved": str(p.resolve()) if p.exists() else None,
            })
    return {
        "devices": devices,
        "note": "Read-only enumeration only. No serial I/O in Phase 3.",
    }
