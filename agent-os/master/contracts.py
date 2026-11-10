"""Pydantic contracts for Master / Dot exchange."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class IntentKind(str, Enum):
    UNKNOWN = "unknown"
    GREETING = "greeting"
    STATUS = "status"
    PROJECT_LIST = "project_list"
    PROJECT_CREATE = "project_create"
    PROJECT_SWITCH = "project_switch"
    PROJECT_CONTINUE = "project_continue"
    PROJECT_STATUS = "project_status"
    PROJECT_NOTE = "project_note"
    PROJECT_DECISION = "project_decision"
    PROJECT_ARCHIVE = "project_archive"
    TASK_CREATE = "task_create"
    TASK_LIST = "task_list"
    TASK_UPDATE = "task_update"
    CHECKPOINT_CREATE = "checkpoint_create"
    CHECKPOINT_RESTORE = "checkpoint_restore"
    HARDWARE_DISCOVERY = "hardware_discovery"
    HARDWARE_BRINGUP = "hardware_bringup"
    DEVICE_LIST_DIR = "device_list_dir"
    DEVICE_READ_FILE = "device_read_file"
    DEVICE_WRITE_FILE = "device_write_file"
    DEVICE_CREATE_DIR = "device_create_dir"
    DEVICE_FILE_INFO = "device_file_info"
    DEVICE_SYSTEM_INFO = "device_system_info"
    DEVICE_TOOLCHAINS = "device_toolchains"
    DEVICE_RUN_COMMAND = "device_run_command"
    DEVICE_LIST_TOOLS = "device_list_tools"
    DEVICE_AUDIT = "device_audit"
    CAPABILITY_QUERY = "capability_query"
    GENERAL = "general"


class RiskLevel(str, Enum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


class InteractRequest(BaseModel):
    """Inbound request from Dot (or CLI tests)."""

    text: str = Field(..., min_length=1, description="User utterance or typed command")
    source: str = Field(default="dot", description="mark|dot|cli|dashboard")
    session_id: Optional[str] = None
    project_id: Optional[str] = None
    mark_confirm_available: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class Intent(BaseModel):
    kind: IntentKind = IntentKind.UNKNOWN
    project_ref: Optional[str] = None
    urgency: str = "normal"
    needs_cloud: bool = False
    agent_hints: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.L0
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    notes: str = ""


class NeedsConfirm(BaseModel):
    id: str
    level: RiskLevel
    action: str
    preview: str
    expires_at: Optional[str] = None


class InteractResponse(BaseModel):
    """Structured payload Dot returns to Mark."""

    speech: str
    intent: Intent
    project_id: Optional[str] = None
    capability: Optional[str] = None
    hud: Optional[dict[str, str]] = None
    needs_confirm: Optional[NeedsConfirm] = None
    status: str = "ok"  # ok|degraded|error
    evidence: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    ollama: str
    model: str
