"""ModelGateway invocation policy — timeout, retry, cancellation, metadata."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class FailureKind(str, Enum):
    NONE = "none"
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    MODEL_UNAVAILABLE = "model_unavailable"
    INVALID_RESPONSE = "invalid_response"
    VALIDATION = "validation"
    CANCELLED = "cancelled"
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    SERVER_ERROR = "server_error"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class QualificationStatus(str, Enum):
    QUALIFIED = "QUALIFIED"
    QUALIFIED_WITH_RESTRICTIONS = "QUALIFIED_WITH_RESTRICTIONS"
    NOT_QUALIFIED = "NOT_QUALIFIED"
    NOT_TESTED = "NOT_TESTED"


# Errors that may be retried (transient).
TRANSIENT = {
    FailureKind.TIMEOUT,
    FailureKind.CONNECTION,
    FailureKind.RATE_LIMIT,
    FailureKind.SERVER_ERROR,
    FailureKind.VALIDATION,
    FailureKind.INVALID_RESPONSE,
}

# Permanent — do not retry.
PERMANENT = {
    FailureKind.AUTH,
    FailureKind.MODEL_UNAVAILABLE,
    FailureKind.PROVIDER_UNAVAILABLE,
    FailureKind.UNSUPPORTED,
    FailureKind.CANCELLED,
}


@dataclass
class RetryPolicy:
    max_retries: int = 1
    backoff_s: float = 0.25

    def allow(self, kind: FailureKind, attempt_index: int) -> bool:
        """attempt_index is 0-based completed attempts before this retry decision."""
        if kind in PERMANENT:
            return False
        if kind not in TRANSIENT:
            return False
        return attempt_index < self.max_retries


@dataclass
class CancellationToken:
    """Cooperative cancellation — checked between attempts and during HTTP."""

    _event: threading.Event = field(default_factory=threading.Event)

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise CancelledError("request cancelled")


class CancelledError(Exception):
    pass


@dataclass
class InvocationResult:
    ok: bool
    text: str = ""
    data: Optional[dict[str, Any]] = None
    provider: str = ""
    model: str = ""
    latency_s: float = 0.0
    attempts: int = 1
    failure_kind: FailureKind = FailureKind.NONE
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        """Safe for AgentResult evidence — no secrets."""
        return {
            "ok": self.ok,
            "provider": self.provider,
            "model": self.model,
            "latency_s": self.latency_s,
            "attempts": self.attempts,
            "failure_kind": self.failure_kind.value,
            "error": self.error,
            "metadata": {
                k: v
                for k, v in self.metadata.items()
                if k.lower() not in ("api_key", "authorization", "token", "password")
            },
        }


def redact_error_text(text: str) -> str:
    out = text
    for needle in ("api_key", "API_KEY", "Bearer ", "sk-", "OPENAI_API_KEY", "authorization"):
        if needle in out:
            return f"{out.split(':')[0]}: [redacted]"
    return out[:300]


def classify_http_error(exc: BaseException) -> FailureKind:
    name = type(exc).__name__
    msg = str(exc).lower()
    if isinstance(exc, CancelledError) or "cancelled" in msg:
        return FailureKind.CANCELLED
    # httpx status errors
    resp = getattr(exc, "response", None)
    status = getattr(resp, "status_code", None)
    if status is not None:
        try:
            code = int(status)
        except (TypeError, ValueError):
            code = None
        if code in (401, 403):
            return FailureKind.AUTH
        if code == 404:
            return FailureKind.MODEL_UNAVAILABLE
        if code == 429:
            return FailureKind.RATE_LIMIT
        if code is not None and code >= 500:
            return FailureKind.SERVER_ERROR
    if "timeout" in name.lower() or "timeout" in msg:
        return FailureKind.TIMEOUT
    if "connect" in name.lower() or "connection refused" in msg or "closed" in msg:
        return FailureKind.CONNECTION
    if "401" in msg or "403" in msg or "unauthorized" in msg:
        return FailureKind.AUTH
    if "404" in msg or "not found" in msg:
        return FailureKind.MODEL_UNAVAILABLE
    if "429" in msg or "rate" in msg:
        return FailureKind.RATE_LIMIT
    if "500" in msg or "502" in msg or "503" in msg:
        return FailureKind.SERVER_ERROR
    return FailureKind.UNKNOWN


def remaining_timeout(deadline: float, *, floor: float = 0.0) -> float:
    """Seconds left before deadline. Returns 0 when exhausted (no silent floor)."""
    return max(floor, deadline - time.monotonic())


def monotonic_deadline(timeout_s: float) -> float:
    return time.monotonic() + max(0.01, timeout_s)
