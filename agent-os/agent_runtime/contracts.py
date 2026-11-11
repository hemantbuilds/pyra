"""Agent Runtime contracts — tasks, results, manifests, lifecycle status."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class ExecutionStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"


class AgentManifest(BaseModel):
    """Registration metadata for a specialist (or test) agent."""

    agent_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: str = ""
    version: str = "0.1.0"
    capabilities: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    allowed_tools: list[str] = Field(default_factory=list)
    max_level: str = "L0"
    timeout_s: float = 30.0
    max_retries: int = 0
    framework: str = "native"  # native|pydantic_ai (5c)


class AgentTask(BaseModel):
    """Validated task request from Master → Agent Runtime."""

    task_id: str = Field(..., min_length=1)
    project_id: str = Field(..., min_length=1)
    requesting_component: str = Field(default="master", min_length=1)
    agent_id: Optional[str] = None
    capability: Optional[str] = None
    description: str = Field(..., min_length=1)
    inputs: dict[str, Any] = Field(default_factory=dict)
    project_context: dict[str, Any] = Field(default_factory=dict)
    allowed_capabilities: list[str] = Field(default_factory=list)
    timeout_s: Optional[float] = None
    correlation_id: Optional[str] = None
    max_level: str = "L1"

    @field_validator("project_id")
    @classmethod
    def _project_id_nonempty(cls, v: str) -> str:
        if not str(v).strip():
            raise ValueError("project_id is required")
        return str(v).strip()

    @field_validator("agent_id", "capability")
    @classmethod
    def _strip_optional(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    def resolve_target(self) -> str:
        """Return agent_id or capability key used for resolution."""
        if self.agent_id:
            return self.agent_id
        if self.capability:
            return self.capability
        raise ValueError("agent_id or capability is required")


class AgentResult(BaseModel):
    """Structured agent result returned to Master."""

    agent_id: str
    task_id: str
    project_id: str
    status: ExecutionStatus
    summary: str = ""
    result: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    recommended_next_action: Optional[str] = None
    lifecycle: list[str] = Field(default_factory=list)
    correlation_id: Optional[str] = None

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> Any:
        if isinstance(v, ExecutionStatus):
            return v
        if isinstance(v, str):
            return ExecutionStatus(v.upper())
        return v
