"""Agent Runtime errors."""

from __future__ import annotations


class AgentRuntimeError(Exception):
    """Base runtime error."""


class DuplicateAgentError(AgentRuntimeError):
    pass


class UnknownAgentError(AgentRuntimeError):
    pass


class InvalidTaskError(AgentRuntimeError):
    pass


class InvalidResultError(AgentRuntimeError):
    pass


class AgentTimeoutError(AgentRuntimeError):
    pass


class BrokerAccessDenied(AgentRuntimeError):
    """Raised when AgentBrokerSession rejects a tool before/after Broker."""
