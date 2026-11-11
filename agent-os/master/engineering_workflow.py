"""
Phase 7 — Master-coordinated multi-specialist engineering workflow.

Specialists are invoked only through Agent Runtime. Deterministic execution
(build/program/serial) goes through Engineering OS → Device Broker.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from agent_runtime.contracts import AgentTask, ExecutionStatus
from agent_runtime.service import get_agent_runtime
from project_os.engineering_artifacts import (
    list_engineering_artifacts,
    load_latest_artifact,
    save_engineering_artifact,
)

from .capabilities import CapabilityResult
from .contracts import NeedsConfirm, RiskLevel
from .engineering_service import get_engineering_os
from .project_service import get_project_os


WORKFLOW_KIND = "engineering_workflow"
STAGE_ORDER = [
    "planning",
    "requirements",
    "architecture",
    "hardware",
    "firmware",
    "implementation_build",
    "verification_plan",
    "awaiting_programming_approval",
    "programming",
    "verification_report",
    "documentation",
    "complete",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _work_root() -> Path:
    return Path(get_project_os().work_root)


def _save_state(project_id: str, state: dict[str, Any]) -> str:
    return save_engineering_artifact(
        _work_root(),
        project_id,
        "workflow_state",
        state,
        agent_id="master",
        task_id=state.get("workflow_id", ""),
    )


def _load_state(project_id: str) -> Optional[dict[str, Any]]:
    payload = load_latest_artifact(_work_root(), project_id, "workflow_state")
    if not payload:
        return None
    return payload.get("data")


def _persist_specialist(project_id: str, kind: str, agent_id: str, task_id: str, data: dict) -> str:
    return save_engineering_artifact(
        _work_root(),
        project_id,
        kind,
        data,
        agent_id=agent_id,
        task_id=task_id,
    )


def _run_specialist(
    *,
    agent_id: str,
    project_id: str,
    description: str,
    inputs: dict[str, Any],
    project_context: dict[str, Any],
    correlation_id: Optional[str] = None,
) -> dict[str, Any]:
    runtime = get_agent_runtime()
    task = AgentTask(
        task_id=f"task_{uuid.uuid4().hex[:12]}",
        project_id=project_id,
        requesting_component="master",
        agent_id=agent_id,
        description=description,
        inputs={**inputs, "force_deterministic": True},
        project_context=project_context,
        correlation_id=correlation_id,
        max_level="L0",
    )
    result = runtime.run(task)
    return {
        "agent_id": result.agent_id,
        "task_id": result.task_id,
        "status": result.status.value,
        "summary": result.summary,
        "output": result.result,
        "errors": list(result.errors or []),
        "evidence": list(result.evidence or []),
        "lifecycle": list(result.lifecycle or []),
    }


def _ensure_project(req_text: str, project_id: Optional[str]) -> dict[str, Any]:
    pos = get_project_os()
    if project_id:
        try:
            proj = pos.get(project_id) if hasattr(pos, "get") else None
            if proj:
                return proj
        except Exception:
            pass
    active = pos.active_project()
    if active:
        return active
    # Create a new project for the engineering request
    name = "Embedded Bring-up"
    if "led" in req_text.lower():
        name = "LED Blink Bring-up"
    return pos.create(
        name=name,
        goal=req_text[:500],
        description=req_text[:2000],
        make_active=True,
    )


def _bounded_ctx(proj: dict[str, Any]) -> dict[str, Any]:
    return {
        "project_id": proj["id"],
        "name": proj.get("name"),
        "slug": proj.get("slug"),
        "status": proj.get("status"),
        "workspace_path": proj.get("workspace_path"),
        "description": (proj.get("description") or "")[:500],
    }


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _find_firmware_artifact(workspace: Path) -> Optional[Path]:
    candidates = [
        workspace / "firmware" / "zephyr_blinky" / "build" / "zephyr" / "zephyr.bin",
        workspace / "firmware" / "zephyr_blinky" / "build" / "zephyr" / "zephyr.elf",
        workspace / "app" / "build" / "zephyr" / "zephyr.bin",
        workspace / "app" / "build" / "zephyr" / "zephyr.elf",
        workspace / "build" / "zephyr" / "zephyr.bin",
    ]
    for c in candidates:
        if c.is_file():
            return c
    # Prefer zephyr.bin anywhere under the workspace build trees
    for pattern in ("**/zephyr/zephyr.bin", "**/build/**/*.bin"):
        hits = sorted(workspace.glob(pattern))
        if hits:
            return hits[0]
    return None


def run_engineering_workflow(
    *,
    request_text: str,
    project_id: Optional[str] = None,
    session_id: Optional[str] = None,
    confirm_id: Optional[str] = None,
    confirm_approved: bool = False,
    skip_live_discovery: bool = False,
    inject_usb: list[dict[str, Any]] | None = None,
    inject_serial: list[dict[str, Any]] | None = None,
) -> CapabilityResult:
    """
    Full multi-specialist workflow. Returns needs_confirm when programming is ready.
    Resumes from Project OS workflow_state when confirm_id matches.
    """
    proj = _ensure_project(request_text, project_id)
    pid = proj["id"]
    ctx = _bounded_ctx(proj)
    workspace = Path(proj["workspace_path"])
    records: list[dict[str, Any]] = []

    # Resume path after human approval
    prior = _load_state(pid)
    if confirm_id and prior and prior.get("approval", {}).get("confirm_id") == confirm_id:
        return _resume_after_approval(
            proj=proj,
            state=prior,
            approved=confirm_approved,
            session_id=session_id,
            records=records,
        )

    workflow_id = f"wf_{uuid.uuid4().hex[:12]}"
    state: dict[str, Any] = {
        "workflow_id": workflow_id,
        "kind": WORKFLOW_KIND,
        "project_id": pid,
        "request_text": request_text,
        "stage": "planning",
        "started_at": _now(),
        "stages": {},
        "approval": None,
        "overall_status": "running",
    }

    # --- Planning ---
    plan_res = _run_specialist(
        agent_id="planning",
        project_id=pid,
        description=request_text,
        inputs={},
        project_context=ctx,
        correlation_id=session_id,
    )
    records.append(plan_res)
    if plan_res["status"] != ExecutionStatus.COMPLETED.value:
        return _fail(pid, state, "Planning specialist failed", records)
    plan_out = plan_res["output"] or {}
    _persist_specialist(pid, "project_plan", "planning", plan_res["task_id"], plan_out)
    state["stages"]["planning"] = plan_res
    try:
        get_project_os().add_task(
            project_id=pid,
            title="Engineering workflow",
            description=plan_out.get("objective") or request_text[:300],
        )
    except Exception:
        pass

    # --- Requirements ---
    req_res = _run_specialist(
        agent_id="requirements",
        project_id=pid,
        description="Derive system requirements for the engineering objective",
        inputs={"project_plan": plan_out},
        project_context=ctx,
        correlation_id=session_id,
    )
    records.append(req_res)
    if req_res["status"] != ExecutionStatus.COMPLETED.value:
        return _fail(pid, state, "Requirements specialist failed", records)
    req_out = req_res["output"] or {}
    _persist_specialist(pid, "requirements", "requirements", req_res["task_id"], req_out)
    state["stages"]["requirements"] = req_res

    # --- Architecture ---
    arch_res = _run_specialist(
        agent_id="architecture",
        project_id=pid,
        description="Develop system architecture for the embedded project",
        inputs={"requirements": req_out, "project_plan": plan_out},
        project_context=ctx,
        correlation_id=session_id,
    )
    records.append(arch_res)
    if arch_res["status"] != ExecutionStatus.COMPLETED.value:
        return _fail(pid, state, "Architecture specialist failed", records)
    arch_out = arch_res["output"] or {}
    _persist_specialist(pid, "system_architecture", "architecture", arch_res["task_id"], arch_out)
    state["stages"]["architecture"] = arch_res

    # --- Hardware discovery (Engineering OS) + specialist ---
    eng = get_engineering_os()
    discovery = eng.discover_hardware(project_id=pid, save_artifact=True)
    evidence = discovery.get("evidence") or {}
    if inject_usb is not None:
        evidence["usb_devices"] = list(inject_usb)
    if inject_serial is not None:
        evidence["serial_devices"] = list(inject_serial)

    # Prefer board id from bring-up style identification
    board_id_info: dict[str, Any] = {}
    try:
        from engineering_os.board_id import resolve_board_identification

        board_id_info = resolve_board_identification(
            usb_devices=list(evidence.get("usb_devices") or []),
            serial_devices=list(evidence.get("serial_devices") or []),
        )
    except Exception as exc:  # noqa: BLE001
        board_id_info = {"error": str(exc), "confidence": "unknown"}

    hw_res = _run_specialist(
        agent_id="hardware_eng",
        project_id=pid,
        description="Analyze discovered hardware for the project",
        inputs={
            "board_identification": board_id_info,
            "discovery": {
                "usb_count": len(evidence.get("usb_devices") or []),
                "serial_count": len(evidence.get("serial_devices") or []),
                "identifications": evidence.get("identifications"),
            },
        },
        project_context=ctx,
        correlation_id=session_id,
    )
    records.append(hw_res)
    if hw_res["status"] != ExecutionStatus.COMPLETED.value:
        return _fail(pid, state, "Hardware specialist failed", records)
    hw_out = hw_res["output"] or {}
    # Attach zephyr board from identification if present
    if board_id_info.get("zephyr_board") and not hw_out.get("programming_method"):
        hw_out = {**hw_out, "zephyr_board": board_id_info.get("zephyr_board")}
    elif board_id_info.get("zephyr_board"):
        hw_out = {**hw_out, "zephyr_board": board_id_info.get("zephyr_board")}
    _persist_specialist(pid, "hardware_design", "hardware_eng", hw_res["task_id"], hw_out)
    state["stages"]["hardware"] = hw_res
    state["board_identification"] = board_id_info

    # --- Firmware design ---
    fw_res = _run_specialist(
        agent_id="firmware_eng",
        project_id=pid,
        description="Design firmware for LED blink bring-up using approved hardware design",
        inputs={
            "requirements": req_out,
            "architecture": arch_out,
            "hardware_design": hw_out,
            "board_identification": board_id_info,
        },
        project_context=ctx,
        correlation_id=session_id,
    )
    records.append(fw_res)
    if fw_res["status"] != ExecutionStatus.COMPLETED.value:
        return _fail(pid, state, "Firmware specialist failed", records)
    fw_out = fw_res["output"] or {}
    _persist_specialist(pid, "firmware_design", "firmware_eng", fw_res["task_id"], fw_out)
    state["stages"]["firmware"] = fw_res

    # --- Implementation + build (Engineering OS deterministic) ---
    build_report = eng.bringup_build(
        project_id=pid,
        workspace_path=str(workspace),
        request_text=request_text,
        save_artifact=True,
        skip_live_discovery=skip_live_discovery or inject_usb is not None,
        inject_usb=inject_usb,
        inject_serial=inject_serial,
    )
    state["stages"]["implementation_build"] = {
        "overall_status": build_report.get("overall_status"),
        "build_result": build_report.get("build_result"),
        "blocked_operations": build_report.get("blocked_operations"),
        "board_identification": build_report.get("board_identification"),
        "artifact_path": build_report.get("artifact_path"),
        "flash_attempted": False,
    }
    # Prefer board info from build if richer
    if build_report.get("board_identification"):
        state["board_identification"] = build_report["board_identification"]
        board_id_info = build_report["board_identification"]

    # --- Verification plan ---
    vplan_res = _run_specialist(
        agent_id="verification",
        project_id=pid,
        description="Create verification plan from requirements",
        inputs={"mode": "plan", "requirements": req_out},
        project_context=ctx,
        correlation_id=session_id,
    )
    records.append(vplan_res)
    vplan_out = vplan_res.get("output") or {}
    _persist_specialist(pid, "verification_plan", "verification", vplan_res["task_id"], vplan_out)
    state["stages"]["verification_plan"] = vplan_res

    # Prepare programming approval if build produced an artifact
    artifact = _find_firmware_artifact(workspace)
    # Also accept injected/build evidence artifact path
    build_data = build_report.get("build_result") or {}
    if artifact is None and isinstance(build_data, dict):
        ap = build_data.get("artifact_path") or build_data.get("firmware_path")
        if ap and Path(ap).is_file():
            artifact = Path(ap)

    programming_ready = False
    needs_confirm = None
    if artifact and artifact.is_file():
        sha = _sha256_file(artifact)
        board_key = (
            board_id_info.get("board_id")
            or board_id_info.get("profile_id")
            or hw_out.get("board_id")
            or "unknown_board"
        )
        device_identity = (
            board_id_info.get("device_identity")
            or board_id_info.get("usb_identity")
            or str(board_id_info.get("match_key") or board_key)
        )
        programmer = (
            hw_out.get("programming_method")
            or board_id_info.get("flasher")
            or "west_flash"
        )
        memory_address = board_id_info.get("memory_address") or "0x0"
        confirm_token = f"confirm_{uuid.uuid4().hex[:16]}"
        try:
            token = eng.client.broker.mint_programming_approval(
                project_id=pid,
                board_id=str(board_key),
                device_identity=str(device_identity),
                artifact_sha256=sha,
                programmer=str(programmer),
                memory_address=str(memory_address),
                erase_required=False,
                ttl_s=900.0,
                metadata={"confirm_id": confirm_token, "artifact_path": str(artifact)},
            )
            state["approval"] = {
                "confirm_id": confirm_token,
                "approval_id": token.token_id,
                "artifact_path": str(artifact),
                "artifact_sha256": sha,
                "board_id": str(board_key),
                "device_identity": str(device_identity),
                "programmer": str(programmer),
                "memory_address": str(memory_address),
                "erase_required": False,
                "expires_at": token.expires_at,
            }
            state["stage"] = "awaiting_programming_approval"
            state["overall_status"] = "waiting_approval"
            programming_ready = True
            needs_confirm = NeedsConfirm(
                id=confirm_token,
                level=RiskLevel.L3,
                action="program_firmware",
                preview=(
                    f"Program {board_key} with {artifact.name} "
                    f"SHA-256={sha} via {programmer} @ {memory_address}. "
                    f"Say 'approve programming {confirm_token}' to proceed."
                ),
                expires_at=datetime.fromtimestamp(token.expires_at, tz=timezone.utc).isoformat(),
            )
        except Exception as exc:  # noqa: BLE001
            state["approval_error"] = str(exc)
            state["stage"] = "verification_report"
    else:
        state["stage"] = "verification_report"
        state["programming_blocked"] = "No firmware artifact available for programming"

    if programming_ready and needs_confirm:
        _save_state(pid, state)
        speech = (
            f"Engineering workflow planned and built for project {proj.get('name')}. "
            f"Specialists completed planning through firmware design. "
            f"Build status: {build_report.get('overall_status')}. "
            f"Programming requires your approval: {needs_confirm.preview}"
        )
        return CapabilityResult(
            speech=speech,
            capability="engineering_workflow",
            project_id=pid,
            status="ok",
            evidence={
                "phase": 7,
                "mode": WORKFLOW_KIND,
                "workflow_id": workflow_id,
                "stage": state["stage"],
                "overall_status": state["overall_status"],
                "specialist_records": records,
                "build_report": {
                    "overall_status": build_report.get("overall_status"),
                    "flash_attempted": False,
                },
                "approval": state.get("approval"),
                "artifacts": list_engineering_artifacts(_work_root(), pid),
            },
            hud={"title": "Engineering workflow — approval required", "body": speech[:1200]},
            needs_confirm=needs_confirm,
        )

    # No programming — finish verification + docs with available evidence
    return _finalize_without_program(
        proj=proj,
        state=state,
        records=records,
        req_out=req_out,
        plan_out=plan_out,
        arch_out=arch_out,
        hw_out=hw_out,
        fw_out=fw_out,
        vplan_out=vplan_out,
        build_report=build_report,
        session_id=session_id,
    )


def _resume_after_approval(
    *,
    proj: dict[str, Any],
    state: dict[str, Any],
    approved: bool,
    session_id: Optional[str],
    records: list[dict[str, Any]],
) -> CapabilityResult:
    pid = proj["id"]
    ctx = _bounded_ctx(proj)
    approval = state.get("approval") or {}
    if not approved:
        state["stage"] = "verification_report"
        state["overall_status"] = "rejected_by_user"
        state["programming_result"] = {"blocked": True, "reason": "User rejected programming"}
        _save_state(pid, state)
        return _finalize_from_state(proj, state, session_id=session_id, records=records)

    eng = get_engineering_os()
    args = {
        "artifact_path": approval["artifact_path"],
        "artifact_sha256": approval["artifact_sha256"],
        "board_id": approval["board_id"],
        "device_identity": approval["device_identity"],
        "programmer": approval["programmer"],
        "memory_address": approval["memory_address"],
        "erase_required": False,
        "approval_id": approval["approval_id"],
    }
    result = eng.client.call(
        "program_firmware",
        args,
        project_id=pid,
        approval_id=approval["approval_id"],
        max_level="L3",
    )
    prog = {
        "ok": result.ok,
        "status": result.status,
        "error": result.error,
        "data": result.data,
        "success": bool(result.ok),
        "operation_id": result.operation_id,
    }
    state["stages"]["programming"] = prog
    state["programming_result"] = prog
    state["stage"] = "verification_report"

    # Optional serial capture — only when a device path is known (never invent).
    serial_result = {"blocked": True, "reason": "No serial device path in workflow state"}
    device = (state.get("serial_device") or approval.get("serial_device"))
    if device:
        try:
            sr = eng.client.call(
                "serial_capture_passive",
                {"device": device, "duration_s": 2.0},
                project_id=pid,
                max_level="L2",
            )
            if sr.ok:
                serial_result = sr.data
            else:
                serial_result = {"blocked": True, "error": sr.error}
        except Exception as exc:  # noqa: BLE001
            serial_result = {"blocked": True, "error": str(exc)}
    state["serial_result"] = serial_result
    _save_state(pid, state)
    return _finalize_from_state(proj, state, session_id=session_id, records=records)


def _finalize_without_program(
    *,
    proj: dict[str, Any],
    state: dict[str, Any],
    records: list[dict[str, Any]],
    req_out: dict,
    plan_out: dict,
    arch_out: dict,
    hw_out: dict,
    fw_out: dict,
    vplan_out: dict,
    build_report: dict,
    session_id: Optional[str],
) -> CapabilityResult:
    state["programming_result"] = {
        "blocked": True,
        "reason": state.get("programming_blocked") or "Programming not prepared",
    }
    state["stages"]["requirements_out"] = req_out
    state["stages"]["plan_out"] = plan_out
    state["stages"]["arch_out"] = arch_out
    state["stages"]["hw_out"] = hw_out
    state["stages"]["fw_out"] = fw_out
    state["stages"]["vplan_out"] = vplan_out
    state["build_report"] = build_report
    _save_state(proj["id"], state)
    return _finalize_from_state(proj, state, session_id=session_id, records=records)


def _finalize_from_state(
    proj: dict[str, Any],
    state: dict[str, Any],
    *,
    session_id: Optional[str],
    records: list[dict[str, Any]],
) -> CapabilityResult:
    pid = proj["id"]
    ctx = _bounded_ctx(proj)
    plan_out = (state.get("stages") or {}).get("plan_out") or (
        (state.get("stages") or {}).get("planning") or {}
    ).get("output") or {}
    req_out = (state.get("stages") or {}).get("requirements_out") or (
        (state.get("stages") or {}).get("requirements") or {}
    ).get("output") or {}
    arch_out = (state.get("stages") or {}).get("arch_out") or (
        (state.get("stages") or {}).get("architecture") or {}
    ).get("output") or {}
    hw_out = (state.get("stages") or {}).get("hw_out") or (
        (state.get("stages") or {}).get("hardware") or {}
    ).get("output") or {}
    fw_out = (state.get("stages") or {}).get("fw_out") or (
        (state.get("stages") or {}).get("firmware") or {}
    ).get("output") or {}
    vplan_out = (state.get("stages") or {}).get("vplan_out") or (
        (state.get("stages") or {}).get("verification_plan") or {}
    ).get("output") or {}
    build_report = state.get("build_report") or (state.get("stages") or {}).get("implementation_build") or {}
    build_result = {}
    if isinstance(build_report, dict):
        build_result = build_report.get("build_result") or build_report

    vrep_res = _run_specialist(
        agent_id="verification",
        project_id=pid,
        description="Evaluate verification evidence against plan",
        inputs={
            "mode": "report",
            "requirements": req_out,
            "verification_plan": vplan_out,
            "build_result": build_result if isinstance(build_result, dict) else {},
            "programming_result": state.get("programming_result") or {},
            "serial_result": state.get("serial_result") or {},
        },
        project_context=ctx,
        correlation_id=session_id,
    )
    records.append(vrep_res)
    vrep_out = vrep_res.get("output") or {}
    _persist_specialist(pid, "verification_report", "verification", vrep_res["task_id"], vrep_out)

    doc_res = _run_specialist(
        agent_id="documentation",
        project_id=pid,
        description="Produce final engineering report from Project OS evidence",
        inputs={
            "project_plan": plan_out,
            "requirements": req_out,
            "architecture": arch_out,
            "hardware_design": hw_out,
            "firmware_design": fw_out,
            "build_result": build_result if isinstance(build_result, dict) else {},
            "programming_result": state.get("programming_result") or {},
            "verification_report": vrep_out,
            "evidence_refs": list_engineering_artifacts(_work_root(), pid),
            "final_status": vrep_out.get("overall_status") or state.get("overall_status"),
        },
        project_context=ctx,
        correlation_id=session_id,
    )
    records.append(doc_res)
    doc_out = doc_res.get("output") or {}
    path = _persist_specialist(pid, "engineering_report", "documentation", doc_res["task_id"], doc_out)
    state["stages"]["verification_report"] = vrep_res
    state["stages"]["documentation"] = doc_res
    state["stage"] = "complete"
    state["overall_status"] = doc_out.get("final_status") or vrep_out.get("overall_status") or "complete"
    state["completed_at"] = _now()
    _save_state(pid, state)

    speech = (
        f"Engineering workflow complete for {proj.get('name')}. "
        f"Final status: {state['overall_status']}. "
        f"Verification: {vrep_out.get('overall_status', 'n/a')}. "
        f"Report saved under Project OS engineering artifacts."
    )
    return CapabilityResult(
        speech=speech,
        capability="engineering_workflow",
        project_id=pid,
        status="ok",
        evidence={
            "phase": 7,
            "mode": WORKFLOW_KIND,
            "workflow_id": state.get("workflow_id"),
            "stage": state["stage"],
            "overall_status": state["overall_status"],
            "specialist_records": records,
            "verification_report": vrep_out,
            "engineering_report": doc_out,
            "engineering_report_path": path,
            "programming_result": state.get("programming_result"),
            "flash_attempted": bool((state.get("programming_result") or {}).get("success")),
            "hardware_verified": False,
            "artifacts": list_engineering_artifacts(_work_root(), pid),
        },
        hud={"title": "Engineering workflow complete", "body": speech[:1200]},
    )


def _fail(pid: str, state: dict, message: str, records: list) -> CapabilityResult:
    state["overall_status"] = "failed"
    state["error"] = message
    state["completed_at"] = _now()
    _save_state(pid, state)
    return CapabilityResult(
        speech=f"Engineering workflow failed: {message}",
        capability="engineering_workflow",
        project_id=pid,
        status="error",
        evidence={
            "phase": 7,
            "mode": WORKFLOW_KIND,
            "overall_status": "failed",
            "error": message,
            "specialist_records": records,
        },
    )


def handle_approval_utterance(text: str, project_id: Optional[str] = None) -> Optional[CapabilityResult]:
    """Detect approval / rejection of a pending L3 programming confirm."""
    t = (text or "").strip().lower()
    confirm_id = None
    approved = False
    if "approve programming" in t or t.startswith("approve "):
        approved = True
        parts = text.strip().split()
        for p in parts:
            if p.startswith("confirm_"):
                confirm_id = p.strip(".,")
                break
    elif any(x in t for x in ("reject programming", "deny programming", "do not program", "don't program")):
        approved = False
        parts = text.strip().split()
        for p in parts:
            if p.startswith("confirm_"):
                confirm_id = p.strip(".,")
                break
    else:
        return None

    pos = get_project_os()
    proj = None
    if project_id:
        try:
            proj = pos.get(project_id)
        except Exception:
            proj = None
    if proj is None:
        proj = pos.active_project()
    if proj is None:
        return CapabilityResult(
            speech="No active project to apply the programming decision.",
            capability="engineering_workflow",
            status="error",
            evidence={"blocked": "no_project"},
        )
    state = _load_state(proj["id"])
    if not state or not state.get("approval"):
        return CapabilityResult(
            speech="There is no pending programming approval for the active project.",
            capability="engineering_workflow",
            status="error",
            evidence={"blocked": "no_pending_approval"},
        )
    if confirm_id and state["approval"].get("confirm_id") != confirm_id:
        return CapabilityResult(
            speech="That confirmation id does not match the pending programming approval.",
            capability="engineering_workflow",
            status="error",
            evidence={"blocked": "confirm_id_mismatch"},
        )
    confirm_id = state["approval"]["confirm_id"]
    return run_engineering_workflow(
        request_text=state.get("request_text") or "resume",
        project_id=proj["id"],
        confirm_id=confirm_id,
        confirm_approved=approved,
    )
