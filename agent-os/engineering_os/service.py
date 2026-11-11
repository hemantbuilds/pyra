"""Engineering OS facade — discovery (Phase 4) + L2 bring-up build (Phase 6)."""

from __future__ import annotations

from typing import Any, Optional

from device_broker.client import BrokerClient

from .discovery import collect_evidence
from .report import build_report
from .workflow import run_bringup_build


class EngineeringOS:
    def __init__(self, broker_client: BrokerClient):
        self.client = broker_client

    def discover_hardware(
        self,
        *,
        project_id: Optional[str] = None,
        save_artifact: bool = True,
    ) -> dict[str, Any]:
        evidence = collect_evidence(self.client, project_id=project_id)
        report = build_report(evidence)
        artifact_path = None
        memory_saved = False

        if save_artifact and project_id:
            artifact_path = self._save_report(project_id, report, prefix="discovery")

        return {
            "evidence": evidence,
            "report": report,
            "artifact_path": artifact_path,
            "memory_saved": memory_saved,
            "project_id": project_id,
        }

    def bringup_build(
        self,
        *,
        project_id: Optional[str],
        workspace_path: Optional[str] = None,
        request_text: str = "",
        capture_serial: bool = False,
        serial_device: Optional[str] = None,
        save_artifact: bool = True,
        **workflow_kwargs: Any,
    ) -> dict[str, Any]:
        """Phase 6 deterministic bring-up: identify → prepare blinky → L2 build."""
        result = run_bringup_build(
            self.client,
            project_id=project_id,
            workspace_path=workspace_path,
            request_text=request_text,
            capture_serial=capture_serial,
            serial_device=serial_device,
            **workflow_kwargs,
        )
        artifact_path = None
        if save_artifact and project_id:
            artifact_path = self._save_text(
                project_id,
                prefix="bringup",
                text=result.get("speech") or "",
                json_body=result,
            )
        result["artifact_path"] = artifact_path
        return result

    def _save_report(self, project_id: str, report: dict[str, Any], *, prefix: str) -> Optional[str]:
        return self._save_text(
            project_id,
            prefix=prefix,
            text=report.get("text") or "",
            json_body=report.get("structured") or report,
        )

    def _save_text(
        self,
        project_id: str,
        *,
        prefix: str,
        text: str,
        json_body: Any,
    ) -> Optional[str]:
        from datetime import datetime, timezone
        import json
        from pathlib import Path

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        work_root = self.client.broker.policy.work_root
        reports = Path(work_root) / "projects" / project_id / "reports"
        txt_path = str(reports / f"{prefix}_{stamp}.txt")
        json_path = str(reports / f"{prefix}_{stamp}.json")
        r1 = self.client.call(
            "write_text_file",
            {"path": txt_path, "content": text, "overwrite": True},
            principal="engineering_os",
            max_level="L1",
            project_id=project_id,
            client="engineering_os",
        )
        self.client.call(
            "write_text_file",
            {
                "path": json_path,
                "content": json.dumps(json_body, indent=2, default=str),
                "overwrite": True,
            },
            principal="engineering_os",
            max_level="L1",
            project_id=project_id,
            client="engineering_os",
        )
        if r1.ok:
            return (r1.data or {}).get("path")
        return None
