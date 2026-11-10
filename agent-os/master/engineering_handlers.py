"""Master handlers for Engineering OS (Phase 4: discovery only)."""

from __future__ import annotations

from .capabilities import CapabilityResult
from .contracts import Intent, IntentKind, InteractRequest
from .engineering_service import get_engineering_os
from .project_service import get_project_os


def handle_engineering(req: InteractRequest, intent: Intent) -> CapabilityResult:
    eng = get_engineering_os()
    pos = get_project_os()
    project_id = req.project_id or pos.active_id()

    # Phase 4: both hardware_discovery and hardware_bringup map to discovery.
    # Bring-up language is acknowledged but flash/erase remain unavailable.
    result = eng.discover_hardware(project_id=project_id, save_artifact=bool(project_id))
    report = result["report"]
    speech = report["speech"]
    if intent.kind == IntentKind.HARDWARE_BRINGUP:
        speech += (
            " Bring-up beyond discovery is not enabled yet "
            "(no flash, erase, reset, or serial I/O in Phase 4)."
        )

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
