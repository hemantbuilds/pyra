"""Phase 7 live architecture smoke — Mark/Dot-shaped request through Master."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from agent_runtime.service import reset_agent_runtime
from master import capabilities
from master.broker_service import reset_broker
from master.contracts import InteractRequest
from master.engineering_service import reset_engineering_os
from master.orchestrator import Orchestrator
from master.project_service import reset_project_os
from project_os.engineering_artifacts import list_engineering_artifacts, load_latest_artifact


def main() -> int:
    td = Path(tempfile.mkdtemp(prefix="phase7_demo_", dir="/home/hem/pyra"))
    work = td / "PyraWork"
    work.mkdir()
    (work / "global").mkdir()
    (work / "projects").mkdir()
    capabilities.reset_registry()
    reset_project_os(work)
    reset_broker(work)
    reset_engineering_os()
    reset_agent_runtime(bootstrap=True)

    orch = Orchestrator()
    text = (
        "Mark, I want to start an embedded project using the development board connected "
        "to this Linux device. Identify the hardware, plan the project, analyze the system "
        "requirements, determine the hardware and software architecture, prepare the firmware, "
        "build it, ask for my approval before programming, program the board, test it, and "
        "prepare a complete engineering report."
    )
    req = InteractRequest(text=text, source="mark", metadata={"from_mark": True})
    resp = orch.handle(req)

    out = {
        "intent": resp.intent.kind.value,
        "capability": resp.capability,
        "status": resp.status,
        "project_id": resp.project_id,
        "needs_confirm": resp.needs_confirm.model_dump() if resp.needs_confirm else None,
        "speech": resp.speech,
        "overall_status": (resp.evidence or {}).get("overall_status"),
        "stage": (resp.evidence or {}).get("stage"),
        "specialist_agents": sorted(
            {
                r.get("agent_id")
                for r in (resp.evidence or {}).get("specialist_records") or []
                if r.get("agent_id")
            }
        ),
        "flash_attempted": (resp.evidence or {}).get("flash_attempted"),
        "artifacts": list_engineering_artifacts(work, resp.project_id) if resp.project_id else [],
    }
    report = load_latest_artifact(work, resp.project_id, "engineering_report") if resp.project_id else None
    hw = load_latest_artifact(work, resp.project_id, "hardware_design") if resp.project_id else None
    out["engineering_report_final_status"] = (report or {}).get("data", {}).get("final_status")
    out["hardware_board_id"] = (hw or {}).get("data", {}).get("board_id")
    out["hardware_confidence"] = (hw or {}).get("data", {}).get("confidence")

    path = Path("docs/implementation/phase7_live_demo_raw.json")
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2)[:4000])
    print("WROTE", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
