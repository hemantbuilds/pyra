"""Toolchain / SDK readiness assessment (read-only; never installs)."""

from __future__ import annotations

from typing import Any, Optional


def assess_toolchain(
    *,
    host_info: dict[str, Any],
    toolchains: dict[str, Any],
    probe_tools: dict[str, Any],
    identifications: list[dict[str, Any]],
) -> dict[str, Any]:
    found_names = {
        (x.get("name") or "").lower()
        for x in (toolchains.get("found") or [])
    }
    found_paths = {
        (x.get("name") or "").lower(): x.get("path")
        for x in (toolchains.get("found") or [])
    }
    probe_found = {
        (x.get("name") or "").lower(): x
        for x in (probe_tools.get("found") or [])
    }

    def present(*names: str) -> bool:
        for n in names:
            if n.lower() in found_names or n.lower() in probe_found:
                return True
        return False

    # Aggregate desired tools from top candidates
    wanted_compilers: set[str] = set()
    wanted_sdks: set[str] = set()
    wanted_flashers: set[str] = set()
    wanted_debuggers: set[str] = set()
    wanted_build: set[str] = set()
    for ident in identifications:
        for c in ident.get("candidates") or []:
            wanted_compilers.update(c.get("common_toolchains") or [])
            wanted_sdks.update(c.get("common_sdks") or [])
            wanted_flashers.update(c.get("common_flashers") or [])
            wanted_debuggers.update(c.get("common_debuggers") or [])
            wanted_build.update(c.get("build_systems") or [])

    # Generic host baseline
    compiler = _status(
        present("gcc", "arm-none-eabi-gcc", "clang"),
        detail=_first_path(found_paths, "gcc", "arm-none-eabi-gcc", "clang"),
    )
    build_system = _status(
        present("cmake", "ninja", "make") or bool(wanted_build),
        detail=_first_path(found_paths, "cmake", "ninja", "make"),
        missing_hint="cmake/ninja/make",
    )
    if wanted_build and not present("cmake", "ninja", "make", "pio", "west"):
        build_system = {
            "status": "missing",
            "detail": None,
            "wanted": sorted(wanted_build),
        }
    elif present("cmake"):
        build_system = _status(True, detail=found_paths.get("cmake"))

    # SDK: cannot fully detect ESP-IDF/STM32Cube without filesystem scan; report unknown/partial
    sdk = {
        "status": "unknown",
        "detail": "SDK install paths are not auto-detected in Phase 4",
        "wanted": sorted(wanted_sdks) if wanted_sdks else [],
    }

    programmer = _status(
        any(present(x) for x in (wanted_flashers or {"openocd", "probe-rs", "esptool.py"})),
        detail=", ".join(sorted(probe_found.keys())[:5]) or None,
        missing_hint=", ".join(sorted(wanted_flashers)[:5]) if wanted_flashers else "openocd/probe-rs/esptool",
    )
    debugger = _status(
        any(present(x) for x in (wanted_debuggers or {"openocd", "probe-rs", "pyocd"})),
        detail=", ".join(sorted(probe_found.keys())[:5]) or None,
        missing_hint=", ".join(sorted(wanted_debuggers)[:5]) if wanted_debuggers else "openocd/probe-rs",
    )

    python_pkgs = {
        "status": "unknown",
        "detail": "Python package detection deferred; host Python present"
        if host_info else "unknown",
    }

    components = {
        "compiler": compiler,
        "build_system": build_system,
        "sdk": sdk,
        "programmer": programmer,
        "debugger": debugger,
        "python_environment": python_pkgs,
        "host": {
            "os": host_info.get("system"),
            "machine": host_info.get("machine"),
            "release": host_info.get("release"),
        },
    }

    statuses = [components[k]["status"] for k in (
        "compiler", "build_system", "programmer", "debugger",
    )]
    if all(s == "available" for s in statuses) and sdk["status"] in ("available", "unknown"):
        overall = "partially_ready" if sdk["status"] == "unknown" else "ready"
    elif any(s == "available" for s in statuses):
        overall = "partially_ready"
    elif all(s == "missing" for s in statuses):
        overall = "not_ready"
    else:
        overall = "unknown"

    missing = []
    for label, block in components.items():
        if isinstance(block, dict) and block.get("status") == "missing":
            missing.append({"component": label, "hint": block.get("missing_hint") or block.get("wanted")})

    return {
        "overall": overall,
        "components": components,
        "missing": missing,
        "next_steps": _next_steps(overall, missing, identifications),
    }


def _status(ok: bool, *, detail: Optional[str] = None, missing_hint: Optional[str] = None) -> dict[str, Any]:
    if ok:
        return {"status": "available", "detail": detail}
    return {"status": "missing", "detail": detail, "missing_hint": missing_hint}


def _first_path(paths: dict[str, Any], *names: str) -> Optional[str]:
    for n in names:
        if n.lower() in paths:
            return paths[n.lower()]
    return None


def _next_steps(overall: str, missing: list, identifications: list) -> list[str]:
    steps = []
    if not identifications:
        steps.append("Connect a board/probe over USB and re-run discovery.")
    for ident in identifications:
        if ident.get("confidence") in ("unknown", "possible"):
            steps.append(
                f"For {ident.get('device_ref')}: supply board marking or datasheet; "
                "USB evidence alone is incomplete."
            )
        for u in ident.get("unresolved") or []:
            if u not in steps:
                steps.append(u)
    for m in missing:
        steps.append(f"Install or expose missing tool: {m.get('component')} ({m.get('hint')}).")
    if overall in ("ready", "partially_ready"):
        steps.append(
            "Phase 4 stops at discovery — flashing/bring-up requires a later Engineering OS phase "
            "with L3 approval."
        )
    return steps[:12]
