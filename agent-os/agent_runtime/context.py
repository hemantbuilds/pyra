"""Bounded execution context for a single agent invocation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .broker_session import AgentBrokerSession


@dataclass
class ExecutionContext:
    """
    Information an agent may use for one task.

    project_id is frozen — agents cannot rebind authoritative project identity.
    """

    project_id: str
    task_id: str
    agent_id: str
    project_context: dict[str, Any] = field(default_factory=dict)
    allowed_tools: list[str] = field(default_factory=list)
    max_level: str = "L0"
    timeout_s: float = 30.0
    correlation_id: Optional[str] = None
    broker: Optional[AgentBrokerSession] = None
    deadline_monotonic: Optional[float] = None
    cancel_token: Any = None  # master.invocation.CancellationToken | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "_frozen_project_id", self.project_id)

    @property
    def frozen_project_id(self) -> str:
        return getattr(self, "_frozen_project_id", self.project_id)

    def assert_project_identity(self) -> None:
        if self.project_id != self.frozen_project_id:
            raise RuntimeError(
                f"project identity mutation forbidden: "
                f"{self.project_id!r} != {self.frozen_project_id!r}"
            )

    def raise_if_cancelled(self) -> None:
        token = self.cancel_token
        if token is not None and getattr(token, "cancelled", False):
            from master.invocation import CancelledError

            raise CancelledError("execution cancelled")
