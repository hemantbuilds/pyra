"""L3 operation-bound approval tokens (Phase 7). Broker-minted only."""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ApprovalToken:
    token_id: str
    operation: str  # program_firmware | erase_flash
    project_id: str
    board_id: str
    device_identity: str
    artifact_sha256: str
    programmer: str
    memory_address: str
    erase_required: bool
    expires_at: float
    used: bool = False
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "token_id": self.token_id,
            "operation": self.operation,
            "project_id": self.project_id,
            "board_id": self.board_id,
            "device_identity": self.device_identity,
            "artifact_sha256": self.artifact_sha256,
            "programmer": self.programmer,
            "memory_address": self.memory_address,
            "erase_required": self.erase_required,
            "expires_at": self.expires_at,
            "used": self.used,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }


class ApprovalStore:
    """In-memory Broker-owned approval store (single-use, expiring)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tokens: dict[str, ApprovalToken] = {}

    def mint(
        self,
        *,
        operation: str,
        project_id: str,
        board_id: str,
        device_identity: str,
        artifact_sha256: str,
        programmer: str,
        memory_address: str,
        erase_required: bool = False,
        ttl_s: float = 900.0,
        metadata: dict[str, Any] | None = None,
    ) -> ApprovalToken:
        if operation not in ("program_firmware", "erase_flash"):
            raise ValueError(f"unsupported approval operation: {operation}")
        sha = (artifact_sha256 or "").strip().lower()
        if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise ValueError("artifact_sha256 must be 64-char hex")
        token = ApprovalToken(
            token_id=secrets.token_hex(16),
            operation=operation,
            project_id=project_id,
            board_id=board_id,
            device_identity=device_identity,
            artifact_sha256=sha,
            programmer=programmer,
            memory_address=memory_address,
            erase_required=bool(erase_required),
            expires_at=time.time() + float(ttl_s),
            metadata=dict(metadata or {}),
        )
        with self._lock:
            self._tokens[token.token_id] = token
        return token

    def peek(self, token_id: str) -> Optional[ApprovalToken]:
        with self._lock:
            return self._tokens.get(token_id)

    def validate_and_consume(
        self,
        *,
        token_id: Optional[str],
        operation: str,
        project_id: Optional[str],
        board_id: str,
        device_identity: str,
        artifact_sha256: str,
        programmer: str,
        memory_address: str,
        erase_required: bool = False,
    ) -> ApprovalToken:
        if not token_id:
            raise PermissionError("L3 operation requires approval_id")
        with self._lock:
            token = self._tokens.get(token_id)
            if token is None:
                raise PermissionError("unknown or invalid approval_id")
            if token.used:
                raise PermissionError("approval already used")
            if time.time() > token.expires_at:
                raise PermissionError("approval expired")
            if token.operation != operation:
                raise PermissionError("approval operation mismatch")
            if project_id and token.project_id != project_id:
                raise PermissionError("approval project_id mismatch")
            if token.board_id != board_id:
                raise PermissionError("approval board_id mismatch")
            if token.device_identity != device_identity:
                raise PermissionError("approval device_identity mismatch")
            if token.artifact_sha256 != (artifact_sha256 or "").strip().lower():
                raise PermissionError("approval artifact_sha256 mismatch")
            if token.programmer != programmer:
                raise PermissionError("approval programmer mismatch")
            if token.memory_address != memory_address:
                raise PermissionError("approval memory_address mismatch")
            if bool(token.erase_required) != bool(erase_required):
                raise PermissionError("approval erase_required mismatch")
            token.used = True
            return token

    def invalidate(self, token_id: str) -> bool:
        with self._lock:
            tok = self._tokens.pop(token_id, None)
            return tok is not None


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
