"""
Minimal MCP-compatible stdio server.

Implements a practical subset:
  - initialize / notifications/initialized
  - tools/list
  - tools/call
  - ping

This keeps the broker independent of the full MCP SDK while remaining
usable by MCP clients that speak JSON-RPC 2.0 over stdio.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Optional, TextIO

from ..broker import DeviceBroker
from ..types import CallContext

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "pyra-device-broker", "version": "0.3.0"}


class McpStdioServer:
    def __init__(self, broker: DeviceBroker, *, infile: TextIO | None = None, outfile: TextIO | None = None):
        self.broker = broker
        self.infile = infile or sys.stdin
        self.outfile = outfile or sys.stdout

    def _write(self, message: dict[str, Any]) -> None:
        line = json.dumps(message, ensure_ascii=False)
        self.outfile.write(line + "\n")
        self.outfile.flush()

    def _result(self, id_: Any, result: Any) -> None:
        self._write({"jsonrpc": "2.0", "id": id_, "result": result})

    def _error(self, id_: Any, code: int, message: str) -> None:
        self._write({"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}})

    def handle_message(self, msg: dict[str, Any]) -> None:
        method = msg.get("method")
        id_ = msg.get("id")
        params = msg.get("params") or {}

        if method == "initialize":
            self._result(id_, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
            })
            return

        if method == "notifications/initialized":
            return

        if method == "ping":
            self._result(id_, {})
            return

        if method == "tools/list":
            self._result(id_, {"tools": self.broker.list_tools()})
            return

        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments") or {}
            meta = params.get("_meta") or {}
            if not name:
                self._error(id_, -32602, "missing tool name")
                return
            ctx = CallContext(
                principal=str(meta.get("principal") or "mcp-client"),
                max_level=str(meta.get("max_level") or self.broker.policy.default_max_level),
                project_id=meta.get("project_id"),
                client=str(meta.get("client") or "mcp-stdio"),
            )
            result = self.broker.invoke(str(name), arguments, ctx=ctx)
            # MCP tools/call content format
            payload = result.to_dict()
            self._result(id_, {
                "content": [
                    {"type": "text", "text": json.dumps(payload, ensure_ascii=False)},
                ],
                "structuredContent": payload,
                "isError": not result.ok,
            })
            return

        if id_ is not None:
            self._error(id_, -32601, f"method not found: {method}")

    def serve_forever(self) -> None:
        for line in self.infile:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                self._write({
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "parse error"},
                })
                continue
            if isinstance(msg, dict):
                self.handle_message(msg)


def serve_stdio(broker: DeviceBroker) -> None:
    McpStdioServer(broker).serve_forever()
