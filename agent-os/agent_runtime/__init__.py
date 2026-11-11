"""PYRA Agent Runtime — specialist execution lifecycle (Phase 5b/5c)."""

from .contracts import AgentManifest, AgentResult, AgentTask, ExecutionStatus
from .errors import AgentRuntimeError, DuplicateAgentError, UnknownAgentError
from .registry import AgentRegistry
from .runtime import AgentRuntime
from .service import get_agent_runtime, get_specialist_gateway, reset_agent_runtime

__all__ = [
    "AgentRuntime",
    "AgentRegistry",
    "AgentTask",
    "AgentResult",
    "AgentManifest",
    "ExecutionStatus",
    "AgentRuntimeError",
    "DuplicateAgentError",
    "UnknownAgentError",
    "get_agent_runtime",
    "get_specialist_gateway",
    "reset_agent_runtime",
]

__version__ = "0.2.0"
