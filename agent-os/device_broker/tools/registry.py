"""Tool registry — typed tools with declared permission levels."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from ..permissions import PermissionLevel


ToolHandler = Callable[..., dict[str, Any]]


@dataclass
class ToolSpec:
    name: str
    description: str
    level: PermissionLevel
    handler: ToolHandler
    input_schema: dict[str, Any]
    category: str = "general"


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def get(self, name: str) -> Optional[ToolSpec]:
        return self._tools.get(name)

    def list_tools(self) -> list[ToolSpec]:
        return sorted(self._tools.values(), key=lambda t: t.name)

    def mcp_list(self) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "inputSchema": t.input_schema,
                "annotations": {
                    "permission_level": t.level.label(),
                    "category": t.category,
                },
            }
            for t in self.list_tools()
        ]


def build_default_registry(broker: "DeviceBroker") -> ToolRegistry:  # noqa: F821
    from . import discovery_tools, exec_tools, fs_tools, sysinfo_tools

    reg = ToolRegistry()
    fs_tools.register(reg, broker)
    sysinfo_tools.register(reg, broker)
    exec_tools.register(reg, broker)
    discovery_tools.register(reg, broker)
    return reg
