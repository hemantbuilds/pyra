"""Shared Device Broker types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class AuditStatus(str, Enum):
    REQUESTED = "requested"
    VALIDATED = "validated"
    DENIED = "denied"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ToolResult:
    ok: bool
    tool: str
    status: str  # completed|denied|failed
    level: str
    data: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    operation_id: Optional[str] = None
    project_id: Optional[str] = None
    speech: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "tool": self.tool,
            "status": self.status,
            "level": self.level,
            "data": self.data,
            "error": self.error,
            "operation_id": self.operation_id,
            "project_id": self.project_id,
            "speech": self.speech,
        }


@dataclass
class CallContext:
    principal: str = "master"
    max_level: str = "L1"
    project_id: Optional[str] = None
    client: str = "master"
    approval_id: Optional[str] = None
    # Phase 6.1 — opaque Broker-issued session token. Caller-supplied principal
    # strings alone cannot authorize L2; a valid session_id is required.
    session_id: Optional[str] = None
