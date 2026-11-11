"""Specialist agent protocol — framework-independent for Phase 5b."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .contracts import AgentManifest, AgentResult, AgentTask
from .context import ExecutionContext


class SpecialistAgent(ABC):
    """Base class for runtime-registered agents (native or future PydanticAI)."""

    @abstractmethod
    def manifest(self) -> AgentManifest:
        ...

    @abstractmethod
    def run(self, task: AgentTask, ctx: ExecutionContext) -> AgentResult:
        """
        Execute the task and return a structured result.

        Must use ctx.broker for any host/tool access.
        Must not mutate ctx.project_id.
        """
        ...
