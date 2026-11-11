"""Master handlers for Engineering OS (Phase 4–7)."""

from __future__ import annotations

from .capabilities import CapabilityResult
from .contracts import Intent, IntentKind, InteractRequest
from .engineering_service import get_engineering_os
from .project_service import get_project_os


def handle_engineering(req: InteractRequest, intent: Intent) -> CapabilityResult:
    eng = get_engineering_os()
    pos = get_project_os()
    project_id = req.project_id or pos.active_id()
    active = pos.active_project() if hasattr(pos, "active_project") else None
    workspace = None
    if active:
        workspace = active.get("workspace_path")
    elif project_id:
        try:
            proj = pos.get(project_id) if hasattr(pos, "get") else None
            if proj:
                workspace = proj.get("workspace_path")
        except Exception:
            workspace = None

    if intent.kind == IntentKind.ENGINEERING_WORKFLOW:
        from .engineering_workflow import run_engineering_workflow

        return run_engineering_workflow(
            request_text=req.text or "",
            project_id=project_id,
            session_id=req.session_id,
        )

    if intent.kind == IntentKind.HARDWARE_BRINGUP:
        # Full engineering request phrases upgrade to Phase 7 workflow
        t = (req.text or "").lower()
        upgrade_keys = (
            "engineering report",
            "project plan",
            "system requirements",
            "system architecture",
            "approve before programming",
            "complete engineering",
            "embedded project",
            "plan the project",
            "firmware design",
        )
        if sum(1 for k in upgrade_keys if k in t) >= 2 or "engineering report" in t:
            from .engineering_workflow import run_engineering_workflow

            return run_engineering_workflow(
                request_text=req.text or "",
                project_id=project_id,
                session_id=req.session_id,
            )

        result = eng.bringup_build(
            project_id=project_id,
            workspace_path=workspace,
            request_text=req.text or "",
            save_artifact=bool(project_id),
        )
        speech = result.get("speech") or "Bring-up workflow finished."
        evidence = {
            "phase": 6,
            "mode": "bringup_build",
            "flash_attempted": False,
            "hardware_verified": False,
            "hardcoded_arduino": False,
            "overall_status": result.get("overall_status"),
            "project_id": project_id,
            "operation_id": result.get("operation_id"),
            "board_identification": result.get("board_identification"),
            "build_result": result.get("build_result"),
            "blocked_operations": result.get("blocked_operations"),
            "artifact_path": result.get("artifact_path"),
            "report": result,
        }
        return CapabilityResult(
            speech=speech,
            capability="engineering_os",
            project_id=project_id,
            status="ok",
            evidence=evidence,
            hud={
                "title": "Engineering bring-up (L2 build)",
                "body": speech[:1200],
            },
        )

    # Phase 4 discovery path (unchanged behaviour)
    result = eng.discover_hardware(project_id=project_id, save_artifact=bool(project_id))
    report = result["report"]
    speech = report["speech"]

    evidence = {
        "phase": 4,
        "mode": "discovery",
        "flash_attempted": False,
        "hardcoded_arduino": False,
        "project_id": project_id,
        "artifact_path": result.get("artifact_path"),
        "overall_readiness": (result.get("evidence") or {})
            .get("toolchain_assessment", {})
            .get("overall"),
        "identifications": (result.get("evidence") or {}).get("identifications"),
        "presence": (result.get("evidence") or {}).get("presence"),
        "report_text": report.get("text"),
    }

    return CapabilityResult(
        speech=speech,
        capability="engineering_os",
        project_id=project_id,
        status="ok",
        evidence=evidence,
        hud={
            "title": "Hardware discovery",
            "body": (report.get("text") or "")[:1200],
        },
    )
