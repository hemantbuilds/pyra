"""In-process Device Broker client used by Master."""

from __future__ import annotations

from typing import Any, Optional

from .broker import DeviceBroker
from .types import CallContext, ToolResult


class BrokerClient:
    """Thin wrapper so Master never touches host APIs directly."""

    def __init__(self, broker: DeviceBroker):
        self.broker = broker

    def list_tools(self) -> list[dict[str, Any]]:
        return self.broker.list_tools()

    def call(
        self,
        tool: str,
        arguments: dict[str, Any] | None = None,
        *,
        principal: str = "master",
        max_level: str = "L1",
        project_id: Optional[str] = None,
        client: str = "master",
    ) -> ToolResult:
        return self.broker.invoke(
            tool,
            arguments or {},
            ctx=CallContext(
                principal=principal,
                max_level=max_level,
                project_id=project_id,
                client=client,
            ),
        )
