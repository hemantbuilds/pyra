"""In-process Device Broker client used by Master and Agent Runtime."""

from __future__ import annotations

from typing import Any, Optional

from .broker import DeviceBroker
from .types import CallContext, ToolResult


class BrokerClient:
    """
    Thin wrapper so Master/agents never touch host APIs directly (ADR-001).

    Phase 6.1: L2 capability is bound to a Broker-issued session_id created via
    DeviceBroker.create_client(...). Caller-supplied principal strings cannot
    forge Engineering OS L2 trust.
    """

    def __init__(
        self,
        broker: DeviceBroker,
        *,
        session_id: Optional[str] = None,
        default_principal: str = "master",
        default_client: str = "master",
        default_max_level: str = "L1",
    ):
        self.broker = broker
        self.session_id = session_id
        self.default_principal = default_principal
        self.default_client = default_client
        self.default_max_level = default_max_level

    def list_tools(self) -> list[dict[str, Any]]:
        return self.broker.list_tools()

    def call(
        self,
        tool: str,
        arguments: dict[str, Any] | None = None,
        *,
        principal: Optional[str] = None,
        max_level: Optional[str] = None,
        project_id: Optional[str] = None,
        client: Optional[str] = None,
        approval_id: Optional[str] = None,
    ) -> ToolResult:
        return self.broker.invoke(
            tool,
            arguments or {},
            ctx=CallContext(
                principal=principal if principal is not None else self.default_principal,
                max_level=max_level if max_level is not None else self.default_max_level,
                project_id=project_id,
                client=client if client is not None else self.default_client,
                session_id=self.session_id,
                approval_id=approval_id,
            ),
        )
