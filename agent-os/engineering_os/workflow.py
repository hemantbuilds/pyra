"""Deterministic Engineering OS L2 bring-up workflow (Phase 6)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from device_broker.client import BrokerClient

from .board_id import resolve_board_identification
from .build_env import assess_build_compatibility, discover_build_tools, inspect_project_build_system
from .discovery import collect_evidence
from .firmware_prep import prepare_zephyr_blinky_via_broker
from . import states


def run_bringup_build(
    client: BrokerClient,
    *,
    project_id: Optional[str],
    workspace_path: Optional[str],
    request_text: str = "",
    capture_serial: bool = False,
    serial_device: Optional[str] = None,
    which=None,
    version_runner=None,
    inject_usb: list[dict[str, Any]] | None = None,
    inject_serial: list[dict[str, Any]] | None = None,
    skip_live_discovery: bool = False,
) -> dict[str, Any]:
    """
    Orchestrate: discover → identify → toolchain → prepare blinky → L2 west build.

    Never flashes. Never treats model output as execution evidence.
    Injectable discovery lists support automated e2e tests without hardware.
    """
    request_id = f"req_{uuid4().hex[:12]}"
    operation_id = None
    started = datetime.now(timezone.utc).isoformat()
    warnings: list[str] = []
    blocked: list[str] = []
    remaining: list[str] = []

    report: dict[str, Any] = {
        "request_id": request_id,
        "project_id": project_id,
        "operation_id": None,
        "requested_operation": "bringup_build",
        "request_text": request_text,
        "phase": 6,
        "started_at": started,
        "discovered_hardware": {},
        "board_identification": {},
        "toolchain_discovery": {},
        "selected_build_system": None,
        "project_preparation": {},
        "build_result": None,
        "build_evidence": None,
        "serial_result": None,
        "blocked_operations": blocked,
        "remaining_actions": remaining,
        "warnings": warnings,
        "overall_status": states.PLANNED,
        "flash_attempted": False,
        "hardware_verified": False,
    }

    if not project_id or not workspace_path:
        report["overall_status"] = states.BLOCKED
        blocked.append("Active Project OS project with workspace is required")
        remaining.append("Create or select a project via Project OS")
        report["speech"] = _speech(report)
        return report

    # 1–2. Discovery
    if skip_live_discovery:
        usb = list(inject_usb or [])
        serial = list(inject_serial or [])
        evidence = {
            "usb_devices": usb,
            "serial_devices": serial,
            "debug_probes": {},
            "identifications": [],
            "mode": "injected",
        }
    else:
        evidence = collect_evidence(client, project_id=project_id)
        usb = list(evidence.get("usb_devices") or [])
        serial = list(evidence.get("serial_devices") or [])
        if inject_usb is not None:
            usb = list(inject_usb)
            evidence["usb_devices"] = usb
        if inject_serial is not None:
            serial = list(inject_serial)
            evidence["serial_devices"] = serial

    report["discovered_hardware"] = {
        "usb_count": len(usb),
        "serial_count": len(serial),
        "usb_devices": usb,
        "serial_devices": serial,
        "broker_errors": evidence.get("broker_errors"),
    }

    if not usb and not serial:
        report["overall_status"] = states.BLOCKED
        blocked.append("No connected USB/serial hardware discovered")
        remaining.append("Connect a supported development board / debug probe")
        report["board_identification"] = resolve_board_identification(
            usb_devices=[], serial_devices=[],
        )
        report["speech"] = _speech(report)
        return report

    # 3. Board identification
    board = resolve_board_identification(usb_devices=usb, serial_devices=serial)
    report["board_identification"] = board
    if not board.get("identified"):
        report["overall_status"] = states.BLOCKED
        blocked.append("Board not uniquely identified from hardware evidence")
        remaining.append("Provide clearer USB evidence or select a supported board profile")
        report["speech"] = _speech(report)
        return report

    zephyr_board = board.get("zephyr_board")
    if not zephyr_board:
        report["overall_status"] = states.BLOCKED
        blocked.append("Identified board has no validated Zephyr board target")
        remaining.append("Add zephyr_board to the board profile or choose another board")
        report["speech"] = _speech(report)
        return report

    # 4. Toolchain / build env (prefer Broker L0 inventory; injectable for tests)
    which_fn = which
    if which_fn is None:
        tr = client.call(
            "get_available_toolchains",
            {},
            principal="engineering_os",
            max_level="L0",
            project_id=project_id,
            client="engineering_os",
        )
        found = {
            (x.get("name") or "").lower(): x.get("path")
            for x in ((tr.data or {}).get("found") or [])
        }

        def which_fn(name: str):
            return found.get((name or "").lower())

    tools = discover_build_tools(which=which_fn, version_runner=version_runner)
    markers = inspect_project_build_system(workspace_path)
    compat = assess_build_compatibility(
        tools=tools,
        board_id=board.get("board_id"),
        zephyr_board=zephyr_board,
        project_markers=markers,
    )
    report["toolchain_discovery"] = {"tools": tools, "compatibility": compat, "markers": markers}
    report["selected_build_system"] = "zephyr" if compat.get("ready_to_build") else None

    if not compat.get("ready_to_build"):
        report["overall_status"] = states.BLOCKED
        blocked.append("Build environment incomplete for Zephyr")
        blocked.extend(compat.get("messages") or [])
        remaining.extend([f"Install/configure {m}" for m in (compat.get("missing_dependencies") or [])])
        report["speech"] = _speech(report)
        return report

    # 5. Prepare firmware
    report["overall_status"] = states.RUNNING
    prep = prepare_zephyr_blinky_via_broker(
        client,
        project_id=project_id,
        workspace_path=workspace_path,
        board_id=board["board_id"],
        zephyr_board=zephyr_board,
    )
    report["project_preparation"] = prep
    if not prep.get("ok"):
        report["overall_status"] = states.FAILED
        blocked.append("Firmware preparation failed")
        report["speech"] = _speech(report)
        return report

    # 6. L2 west build via Broker
    build_res = client.call(
        "west_build",
        {
            "board": zephyr_board,
            "source_dir": prep["source_dir"],
        },
        principal="engineering_os",
        max_level="L2",
        project_id=project_id,
        client="engineering_os",
    )
    operation_id = build_res.operation_id
    report["operation_id"] = operation_id
    data = build_res.data or {}
    report["build_result"] = {
        "ok": build_res.ok,
        "status": build_res.status,
        "error": build_res.error,
        "success": data.get("success"),
        "exit_code": data.get("exit_code"),
        "timed_out": data.get("timed_out"),
    }
    report["build_evidence"] = {
        "operation_id": operation_id,
        "project_id": project_id,
        "board_profile_id": board.get("board_id"),
        "build_system": "zephyr/west",
        "toolchain": tools.get("by_id"),
        "executable": data.get("resolved_executable"),
        "argv": data.get("argv"),
        "cwd": data.get("cwd"),
        "started_at": data.get("started_at"),
        "ended_at": data.get("ended_at"),
        "duration_s": data.get("duration_s"),
        "exit_status": data.get("exit_code"),
        "timed_out": data.get("timed_out"),
        "stdout": data.get("stdout"),
        "stderr": data.get("stderr"),
        "artifacts": data.get("artifacts"),
        "success": data.get("success"),
        "flash_attempted": False,
    }

    if build_res.status == "denied":
        report["overall_status"] = states.BLOCKED
        blocked.append(build_res.error or "Broker denied west_build")
    elif not build_res.ok or not data.get("success"):
        report["overall_status"] = states.FAILED
        remaining.append("Inspect build stderr and fix the firmware/project")
    else:
        report["overall_status"] = states.BUILT
        remaining.append("Phase 7: human-approved flash/verify (not available)")
        warnings.append("Firmware was compiled only — LED/hardware operation was not verified")

    # 7. Optional passive serial
    if capture_serial:
        if not serial_device:
            warnings.append("Serial capture requested but no device specified")
        else:
            ser = client.call(
                "serial_capture_passive",
                {"device": serial_device, "duration_s": 1.0, "baudrate": 115200},
                principal="engineering_os",
                max_level="L2",
                project_id=project_id,
                client="engineering_os",
            )
            report["serial_result"] = {
                "ok": ser.ok,
                "status": ser.status,
                "error": ser.error,
                "data": ser.data,
                "tx_attempted": False,
            }

    report["ended_at"] = datetime.now(timezone.utc).isoformat()
    report["speech"] = _speech(report)
    return report


def _speech(report: dict[str, Any]) -> str:
    status = report.get("overall_status")
    board = report.get("board_identification") or {}
    parts: list[str] = []
    hw = report.get("discovered_hardware") or {}
    parts.append(
        f"Discovered {hw.get('usb_count', 0)} USB and {hw.get('serial_count', 0)} serial endpoints."
    )
    if board.get("identified"):
        parts.append(
            f"Hardware evidence matches board profile {board.get('board_id')} "
            f"({board.get('board_name')}) with confidence {board.get('confidence')}."
        )
        if board.get("evidence"):
            parts.append("Identification is evidence-based (USB/profile match), not model invention.")
    else:
        parts.append("Board was not uniquely identified from hardware evidence.")

    if status == states.BLOCKED:
        parts.append("Bring-up build is blocked: " + "; ".join(report.get("blocked_operations") or [])[:400])
    elif status == states.FAILED:
        br = report.get("build_result") or {}
        parts.append(
            f"Build failed (exit {br.get('exit_code')}). Compilation did not succeed."
        )
    elif status == states.BUILT:
        parts.append(
            "Prepared the Zephyr blinky application and compiled it successfully. "
            "No firmware was flashed. Hardware LED operation has not been verified."
        )
    else:
        parts.append(f"Bring-up status: {status}.")

    parts.append("Flash, erase, and persistent configuration remain unavailable (Phase 7).")
    return " ".join(parts)
