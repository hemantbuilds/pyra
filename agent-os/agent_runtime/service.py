"""Lazy Agent Runtime singleton for Master."""

from __future__ import annotations

from typing import Optional

from device_broker.client import BrokerClient

from .bootstrap import bootstrap_builtin_agents, reset_bootstrap_flag
from .registry import AgentRegistry
from .runtime import AgentRuntime

_RUNTIME: Optional[AgentRuntime] = None
_GATEWAY = None


def get_specialist_gateway():
    """Shared ModelGateway used by PydanticAI specialists (testable override)."""
    global _GATEWAY
    if _GATEWAY is None:
        from master.model_gateway import ModelGateway

        _GATEWAY = ModelGateway()
    return _GATEWAY


def reset_specialist_gateway(gateway=None):
    global _GATEWAY
    _GATEWAY = gateway
    if _GATEWAY is None:
        from master.model_gateway import ModelGateway

        _GATEWAY = ModelGateway()
    return _GATEWAY


def get_agent_runtime() -> AgentRuntime:
    global _RUNTIME
    if _RUNTIME is None:
        from master.broker_service import get_broker_client

        _RUNTIME = AgentRuntime(
            registry=AgentRegistry(),
            broker_client=get_broker_client(),
        )
        bootstrap_builtin_agents(_RUNTIME)
    return _RUNTIME


def reset_agent_runtime(
    broker_client: BrokerClient | None = None,
    *,
    bootstrap: bool = True,
) -> AgentRuntime:
    """Tests: rebuild runtime, optionally with an explicit BrokerClient."""
    global _RUNTIME
    reset_bootstrap_flag()
    reset_specialist_gateway()
    if broker_client is None:
        from master.broker_service import get_broker_client

        broker_client = get_broker_client()
    _RUNTIME = AgentRuntime(registry=AgentRegistry(), broker_client=broker_client)
    if bootstrap:
        bootstrap_builtin_agents(_RUNTIME)
    return _RUNTIME
