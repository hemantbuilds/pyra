"""Master capability handlers that go through Device Broker only."""

from __future__ import annotations

import re
from typing import Any, Optional

from .broker_service import get_broker_client
from .capabilities import CapabilityResult
from .contracts import Intent, IntentKind, InteractRequest
from .project_service import get_project_os


def handle_device(req: InteractRequest, intent: Intent) -> CapabilityResult:
    client = get_broker_client()
    text = req.text.strip()
    project_id = req.project_id or get_project_os().active_id()

    try:
        if intent.kind == IntentKind.DEVICE_LIST_DIR:
            path = _extract_path(text) or "."
            return _call(client, "list_directory", {"path": path}, project_id)

        if intent.kind == IntentKind.DEVICE_READ_FILE:
            path = _extract_path(text) or _extract_quoted(text)
            if not path:
                return _err("Specify a file path to read.")
            return _call(client, "read_text_file", {"path": path}, project_id)

        if intent.kind == IntentKind.DEVICE_WRITE_FILE:
            path, content = _extract_write(text)
            if not path:
                return _err("Specify a path and content to write.")
            return _call(
                client,
                "write_text_file",
                {"path": path, "content": content or "", "overwrite": True},
                project_id,
            )

        if intent.kind == IntentKind.DEVICE_CREATE_DIR:
            path = _extract_dirname(text) or _extract_path(text)
            if not path:
                return _err("Specify a directory name to create.")
            return _call(client, "create_directory", {"path": path}, project_id)

        if intent.kind == IntentKind.DEVICE_SYSTEM_INFO:
            return _call(client, "get_system_info", {}, project_id)

        if intent.kind == IntentKind.DEVICE_TOOLCHAINS:
            r1 = client.call("get_available_toolchains", {}, project_id=project_id)
            r2 = client.call("get_installed_tool_versions", {}, project_id=project_id)
            ok = r1.ok and r2.ok
            speech = r1.speech
            if r2.ok:
                speech += " Version probes recorded."
            return CapabilityResult(
                speech=speech if ok else (r1.error or r2.error or "toolchain probe failed"),
                capability="device_broker",
                project_id=project_id,
                status="ok" if ok else "error",
                evidence={
                    "toolchains": r1.to_dict(),
                    "versions": r2.to_dict(),
                },
                hud={"title": "Toolchains", "body": speech},
            )

        if intent.kind == IntentKind.DEVICE_RUN_COMMAND:
            argv = _extract_version_command(text)
            if not argv:
                return _err(
                    "Only allowlisted version-check commands are available. "
                    "Example: run the approved python version check."
                )
            return _call(client, "run_allowed_command", {"argv": argv}, project_id)

        if intent.kind == IntentKind.DEVICE_LIST_TOOLS:
            return _call(client, "list_broker_tools", {}, project_id)

        if intent.kind == IntentKind.DEVICE_AUDIT:
            return _call(client, "get_execution_history", {"limit": 10}, project_id)

        if intent.kind == IntentKind.DEVICE_FILE_INFO:
            path = _extract_path(text) or _extract_quoted(text)
            if not path:
                return _err("Specify a path for file info.")
            return _call(client, "get_file_info", {"path": path}, project_id)

        return _err(f"Unsupported device intent: {intent.kind.value}")
    except Exception as exc:  # noqa: BLE001
        return _err(f"Device Broker error: {exc}")


def _call(client, tool: str, args: dict[str, Any], project_id: Optional[str]) -> CapabilityResult:
    result = client.call(tool, args, project_id=project_id, principal="master", max_level="L1")
    return CapabilityResult(
        speech=result.speech or (result.error or tool),
        capability="device_broker",
        project_id=result.project_id or project_id,
        status="ok" if result.ok else ("error" if result.status == "failed" else "error"),
        evidence=result.to_dict(),
        hud={"title": f"Device Broker · {tool}", "body": result.speech or result.error or ""},
    )


def _err(speech: str) -> CapabilityResult:
    return CapabilityResult(
        speech=speech,
        capability="device_broker",
        status="error",
        evidence={},
    )


def _extract_quoted(text: str) -> Optional[str]:
    m = re.search(r"[\"']([^\"']+)[\"']", text)
    return m.group(1) if m else None


def _extract_path(text: str) -> Optional[str]:
    q = _extract_quoted(text)
    if q:
        return q
    # "files in my active project workspace" → "."
    t = text.lower()
    if "workspace" in t and ("list" in t or "show" in t or "files" in t):
        return "."
    m = re.search(r"(?i)\b(?:in|path|file|directory|dir)\s+([~\w./-]+)", text)
    if m:
        return m.group(1)
    m = re.search(r"(?i)\bread\s+(?:the\s+)?([~\w./-]+)", text)
    if m:
        return m.group(1)
    return None


def _extract_dirname(text: str) -> Optional[str]:
    q = _extract_quoted(text)
    if q:
        return q
    m = re.search(
        r"(?i)(?:directory|dir|folder)\s+(?:called|named)\s+[\"']?([~\w./-]+)[\"']?",
        text,
    )
    if m:
        return m.group(1)
    m = re.search(r"(?i)create\s+(?:a\s+)?(?:directory|dir|folder)\s+[\"']?([~\w./-]+)[\"']?", text)
    if m:
        return m.group(1)
    return None


def _extract_write(text: str) -> tuple[Optional[str], Optional[str]]:
    # write "hello" to path  OR  write path: content
    m = re.search(r"(?i)write\s+[\"'](.+?)[\"']\s+to\s+([~\w./-]+)", text)
    if m:
        return m.group(2), m.group(1)
    m = re.search(r"(?i)write\s+(?:to\s+)?([~\w./-]+)\s*:\s*(.+)$", text)
    if m:
        return m.group(1), m.group(2)
    path = _extract_path(text)
    return path, None


def _extract_version_command(text: str) -> Optional[list[str]]:
    t = text.lower()
    if "python" in t:
        return ["python3", "--version"]
    if "git" in t:
        return ["git", "--version"]
    if "cmake" in t:
        return ["cmake", "--version"]
    if "gcc" in t and "arm" in t:
        return ["arm-none-eabi-gcc", "--version"]
    if "gcc" in t:
        return ["gcc", "--version"]
    if "uname" in t or "version-check" in t or "version check" in t or "approved" in t:
        return ["uname", "-a"]
    return None
