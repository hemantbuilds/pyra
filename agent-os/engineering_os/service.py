"""Engineering OS facade — discovery for Phase 4."""

from __future__ import annotations

from typing import Any, Optional

from device_broker.client import BrokerClient

from .discovery import collect_evidence
from .report import build_report


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
            artifact_path = self._save_report(project_id, report)

        return {
            "evidence": evidence,
            "report": report,
            "artifact_path": artifact_path,
            "memory_saved": memory_saved,
            "project_id": project_id,
        }

    def _save_report(self, project_id: str, report: dict[str, Any]) -> Optional[str]:
        """Persist report via Device Broker L1 write into project reports/."""
        from datetime import datetime, timezone
        from pathlib import Path

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        # Absolute path under project reports/ (approved write root)
        work_root = self.client.broker.policy.work_root
        reports = Path(work_root) / "projects" / project_id / "reports"
        txt_path = str(reports / f"discovery_{stamp}.txt")
        json_path = str(reports / f"discovery_{stamp}.json")
        r1 = self.client.call(
            "write_text_file",
            {"path": txt_path, "content": report["text"], "overwrite": True},
            principal="engineering_os",
            max_level="L1",
            project_id=project_id,
            client="engineering_os",
        )
        self.client.call(
            "write_text_file",
            {"path": json_path, "content": report["json"], "overwrite": True},
            principal="engineering_os",
            max_level="L1",
            project_id=project_id,
            client="engineering_os",
        )
        if r1.ok:
            return (r1.data or {}).get("path")
        return None
