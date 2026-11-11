"""In-process agent registry."""

from __future__ import annotations

from typing import Optional

from .agent import SpecialistAgent
from .contracts import AgentManifest
from .errors import DuplicateAgentError, UnknownAgentError


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, SpecialistAgent] = {}
        self._capability_index: dict[str, str] = {}  # capability → agent_id

    def register(self, agent: SpecialistAgent) -> AgentManifest:
        manifest = agent.manifest()
        aid = manifest.agent_id
        if aid in self._agents:
            raise DuplicateAgentError(f"agent already registered: {aid}")
        self._agents[aid] = agent
        for cap in manifest.capabilities:
            # First registrant wins for a capability key
            self._capability_index.setdefault(cap, aid)
        return manifest

    def get(self, agent_id: str) -> SpecialistAgent:
        agent = self._agents.get(agent_id)
        if agent is None:
            raise UnknownAgentError(f"unknown agent: {agent_id}")
        return agent

    def resolve(self, *, agent_id: Optional[str] = None, capability: Optional[str] = None) -> SpecialistAgent:
        if agent_id:
            return self.get(agent_id)
        if capability:
            mapped = self._capability_index.get(capability)
            if mapped is None:
                # Allow capability == agent_id
                if capability in self._agents:
                    return self.get(capability)
                raise UnknownAgentError(f"unknown capability: {capability}")
            return self.get(mapped)
        raise UnknownAgentError("agent_id or capability required")

    def list_agents(self) -> list[AgentManifest]:
        return [a.manifest() for a in self._agents.values()]

    def list_capabilities(self) -> dict[str, str]:
        return dict(self._capability_index)

    def clear(self) -> None:
        self._agents.clear()
        self._capability_index.clear()
