"""
Agent-scoped access to Device Broker via existing BrokerClient.

Device Broker remains the security authority. This session only:
- Restricts tools to the agent allowlist
- Caps max_level (never escalates)
- Forces project_id from the execution context
- Applies call timeouts
- Records operation references for evidence

Does not duplicate Broker policy.
"""

from __future__ import annotations

import concurrent.futures
from typing import Any, Optional

from device_broker.client import BrokerClient
from device_broker.types import ToolResult

from .errors import BrokerAccessDenied


class AgentBrokerSession:
    """Internal tool path: Agent → BrokerClient → Device Broker."""

    def __init__(
        self,
        client: BrokerClient,
        *,
        agent_id: str,
        project_id: str,
        allowed_tools: list[str],
        max_level: str = "L0",
        call_timeout_s: float = 15.0,
    ):
        self._client = client
        self.agent_id = agent_id
        self.project_id = project_id
        self.allowed_tools = set(allowed_tools)
        self.max_level = max_level
        self.call_timeout_s = call_timeout_s
        self.calls: list[dict[str, Any]] = []

    def list_allowed_tools(self) -> list[str]:
        catalog = {t["name"] for t in self._client.list_tools()}
        return sorted(self.allowed_tools & catalog)

    def call(
        self,
        tool: str,
        arguments: dict[str, Any] | None = None,
        *,
        timeout_s: Optional[float] = None,
    ) -> ToolResult:
        if tool not in self.allowed_tools:
            raise BrokerAccessDenied(
                f"tool {tool!r} is not on agent {self.agent_id!r} allowlist"
            )

        timeout = timeout_s if timeout_s is not None else self.call_timeout_s

        def _invoke() -> ToolResult:
            return self._client.call(
                tool,
                arguments or {},
                principal=f"agent:{self.agent_id}",
                max_level=self.max_level,
                project_id=self.project_id,
                client="agent_runtime",
            )

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(_invoke)
                result = fut.result(timeout=timeout)
        except concurrent.futures.TimeoutError as exc:
            raise BrokerAccessDenied(f"broker call timed out: {tool}") from exc

        self.calls.append(
            {
                "tool": tool,
                "ok": result.ok,
                "status": result.status,
                "operation_id": result.operation_id,
                "error": result.error,
                "project_id": result.project_id,
            }
        )

        # Agent cannot escalate; Broker still may deny — surface as structured result.
        return result
