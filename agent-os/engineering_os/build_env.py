"""Build-environment discovery and compatibility (Phase 6)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Optional


_TOOLS = (
    ("west", ("west", "--version")),
    ("cmake", ("cmake", "--version")),
    ("ninja", ("ninja", "--version")),
    ("arm-none-eabi-gcc", ("arm-none-eabi-gcc", "--version")),
    ("git", ("git", "--version")),
    ("python3", ("python3", "--version")),
    ("pio", ("pio", "--version")),
    ("platformio", ("platformio", "--version")),
)


def discover_build_tools(
    *,
    which: Any = None,
    version_runner: Any = None,
) -> dict[str, Any]:
    """
    Discover toolchain executables and versions.

    `which` and `version_runner` are injectable for tests.
    Never installs tools.
    """
    which_fn = which or shutil.which
    tools: list[dict[str, Any]] = []
    for name, argv in _TOOLS:
        path = which_fn(name)
        entry: dict[str, Any] = {
            "id": name,
            "available": bool(path),
            "path": path,
            "version": None,
            "version_output": None,
            "discovery_method": "path_which",
            "validation": "missing" if not path else "present",
        }
        if path and version_runner is not None:
            try:
                out = version_runner(argv)
                entry["version_output"] = str(out)[:500]
                entry["version"] = _first_line(out)
                entry["validation"] = "ok"
            except Exception as exc:  # noqa: BLE001
                entry["validation"] = "version_failed"
                entry["version_output"] = f"{type(exc).__name__}: {exc}"
        elif path:
            entry["validation"] = "present_unverified"
        tools.append(entry)

    by_id = {t["id"]: t for t in tools}
    return {
        "tools": tools,
        "by_id": by_id,
        "zephyr_ready": bool(
            by_id.get("west", {}).get("available")
            and by_id.get("cmake", {}).get("available")
            and by_id.get("arm-none-eabi-gcc", {}).get("available")
        ),
        "platformio_ready": bool(
            by_id.get("pio", {}).get("available") or by_id.get("platformio", {}).get("available")
        ),
        "missing": [t["id"] for t in tools if not t["available"] and t["id"] in (
            "west", "cmake", "ninja", "arm-none-eabi-gcc",
        )],
    }


def inspect_project_build_system(project_dir: str | Path) -> dict[str, Any]:
    """Detect Zephyr / PlatformIO markers without claiming buildability."""
    root = Path(project_dir)
    markers = {
        "west.yml": (root / "west.yml").is_file() or (root / "zephyr" / "west.yml").is_file(),
        "CMakeLists.txt": (root / "CMakeLists.txt").is_file(),
        "prj.conf": (root / "prj.conf").is_file(),
        "platformio.ini": (root / "platformio.ini").is_file(),
    }
    detected: list[str] = []
    if markers["west.yml"] or (markers["CMakeLists.txt"] and markers["prj.conf"]):
        detected.append("zephyr")
    if markers["platformio.ini"]:
        detected.append("platformio")
    return {
        "project_dir": str(root),
        "markers": markers,
        "detected_build_systems": detected,
        "buildable_claim": False,  # never claim buildable from markers alone
        "notes": "Marker presence ≠ validated build environment",
    }


def assess_build_compatibility(
    *,
    tools: dict[str, Any],
    board_id: Optional[str],
    zephyr_board: Optional[str],
    project_markers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    missing = list(tools.get("missing") or [])
    compatible: list[str] = []
    incompatible: list[str] = []
    messages: list[str] = []

    if tools.get("zephyr_ready") and zephyr_board:
        compatible.append("zephyr")
    elif zephyr_board:
        incompatible.append("zephyr")
        messages.append("Zephyr board target known but west/cmake/arm-none-eabi-gcc incomplete")
        for m in missing:
            messages.append(f"missing dependency: {m}")
    else:
        messages.append("No validated Zephyr board target selected")

    if tools.get("platformio_ready"):
        compatible.append("platformio")
    elif (project_markers or {}).get("markers", {}).get("platformio.ini"):
        incompatible.append("platformio")
        messages.append("platformio.ini present but PlatformIO CLI missing")

    ready = bool(compatible) and not (
        zephyr_board and "zephyr" not in compatible
    )
    return {
        "board_id": board_id,
        "zephyr_board": zephyr_board,
        "available_toolchains": [
            t for t in (tools.get("tools") or []) if t.get("available")
        ],
        "missing_dependencies": missing,
        "detected_build_systems": (project_markers or {}).get("detected_build_systems") or [],
        "compatible_build_systems": compatible,
        "incompatible_or_incomplete": incompatible,
        "ready_to_build": ready and "zephyr" in compatible,
        "messages": messages,
    }


def _first_line(text: Any) -> str:
    s = str(text or "").strip().splitlines()
    return s[0][:200] if s else ""
