"""Minimal MCP transport for Device Broker (stdio JSON-RPC)."""

from .server import serve_stdio

__all__ = ["serve_stdio"]
