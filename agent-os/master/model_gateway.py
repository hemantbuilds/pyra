"""Local Ollama client + structured intent extraction (pukky lineage)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

import httpx

from .config import SETTINGS
from .contracts import Intent, IntentKind, RiskLevel
from project_os import textparse

log = logging.getLogger("pyra.master.model")

_INTENT_KINDS = ", ".join(k.value for k in IntentKind)

_INTENT_SYSTEM = f"""You are PYRA Master intent classifier on a Raspberry Pi.
Reply with ONLY one JSON object, no markdown, no commentary.
Schema:
{{
  "kind": one of [{_INTENT_KINDS}],
  "project_ref": string or null,
  "needs_cloud": boolean,
  "agent_hints": string array,
  "risk_level": one of [L0,L1,L2,L3],
  "confidence": number 0..1,
  "notes": short string
}}
Rules:
- hardware_discovery: enumerate/identify connected USB/serial/debug hardware (no flash).
- hardware_bringup: user asked to bring up a board — Phase 4 still runs discovery only (no flash).
- project_*/task_*/checkpoint_*: project management operations.
- device_*: Device Broker ops (list/read/write workspace files, system info, toolchains, allowlisted commands).
- Keep needs_cloud false unless deep engineering reasoning is required.
- Never assume Arduino or any specific MCU without evidence.
"""


def _strip_fences(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"(?is)<think(?:ing)?>.*?</think(?:ing)?>", "", text).strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _extract_json(text: str) -> Optional[dict[str, Any]]:
    cleaned = _strip_fences(text)
    try:
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None


def deterministic_intent(text: str) -> Intent:
    """Rule-based router for clear project/system phrases."""
    t = text.lower().strip()

    # Wake-word greeting only when there is no substantive command after it.
    if any(w in t for w in ("hello", "hi ", "hey pyra", "hey dot", "good morning")):
        remainder = t
        for w in ("hey pyra", "hey dot", "good morning", "hello", "hi"):
            remainder = remainder.replace(w, " ")
        remainder = remainder.strip(" ,!.?:;-")
        if len(remainder) < 4:
            return Intent(kind=IntentKind.GREETING, confidence=0.9, notes="deterministic")

    if any(p in t for p in ("list project", "show project", "my projects", "all projects", "show my active project")):
        return Intent(kind=IntentKind.PROJECT_LIST, confidence=0.9, notes="deterministic")

    if any(p in t for p in ("list task", "show task", "my tasks", "project tasks")):
        return Intent(kind=IntentKind.TASK_LIST, confidence=0.9, notes="deterministic")

    if re.search(r"(?i)\b(add|create|new)\s+(a\s+)?task\b", text):
        return Intent(kind=IntentKind.TASK_CREATE, confidence=0.9, notes="deterministic")

    if re.search(r"(?i)mark .+ as completed|mark .+ complete|\bcomplete\s+(the\s+)?task|\bfinish\s+(the\s+)?task", text):
        return Intent(kind=IntentKind.TASK_UPDATE, confidence=0.9, notes="deterministic")

    if re.search(r"(?i)restore\s+(a\s+|the\s+)?checkpoint", text):
        return Intent(kind=IntentKind.CHECKPOINT_RESTORE, confidence=0.9, notes="deterministic")

    if re.search(r"(?i)(create|save|take)\s+(a\s+)?checkpoint", text):
        return Intent(kind=IntentKind.CHECKPOINT_CREATE, confidence=0.9, notes="deterministic")

    if re.search(r"(?i)save\s+(this\s+)?(engineering\s+)?decision|\bdecision\b", text) and (
        "save" in t or "record" in t or "add" in t
    ):
        return Intent(kind=IntentKind.PROJECT_DECISION, confidence=0.85, notes="deterministic")

    if re.search(r"(?i)(save|add|record)\s+(a\s+|this\s+)?note\b|^\s*note\s*:", text):
        return Intent(kind=IntentKind.PROJECT_NOTE, confidence=0.85, notes="deterministic")

    if re.search(r"(?i)\barchive\s+(the\s+)?project\b", text):
        ref = textparse.extract_project_ref_for_switch(text)
        return Intent(kind=IntentKind.PROJECT_ARCHIVE, project_ref=ref, confidence=0.85, notes="deterministic")

    # Directory creation must win over "… project" substring matches.
    if re.search(r"(?i)create\s+(a\s+)?(directory|dir|folder)\b", text):
        return Intent(kind=IntentKind.DEVICE_CREATE_DIR, risk_level=RiskLevel.L1, confidence=0.9, notes="deterministic")

    if any(p in t for p in ("create project", "new project", "start a project", "start project")) or re.search(
        r"(?i)create\s+(a\s+)?(new\s+)?(?!directory|dir|folder)(.+\s+)?project\b", text
    ):
        name = textparse.extract_project_name_for_create(text)
        return Intent(
            kind=IntentKind.PROJECT_CREATE,
            project_ref=name,
            confidence=0.9,
            notes="deterministic",
        )

    if "switch" in t and "project" in t:
        ref = textparse.extract_project_ref_for_switch(text)
        return Intent(kind=IntentKind.PROJECT_SWITCH, project_ref=ref, confidence=0.9, notes="deterministic")

    if any(p in t for p in ("continue", "resume", "where did we stop", "where were we", "what were we working")):
        ref = textparse.extract_project_ref_for_switch(text)
        # "what were we working on in this project" → continue/status
        if "what were we" in t or "where did we" in t or "where were we" in t:
            return Intent(kind=IntentKind.PROJECT_CONTINUE, project_ref=ref, confidence=0.85, notes="deterministic")
        return Intent(kind=IntentKind.PROJECT_CONTINUE, project_ref=ref, confidence=0.85, notes="deterministic")

    if re.search(r"(?i)project\s+status|status\s+of\s+(the\s+)?project|show\s+(the\s+)?project", text):
        ref = textparse.extract_project_ref_for_switch(text)
        return Intent(kind=IntentKind.PROJECT_STATUS, project_ref=ref, confidence=0.85, notes="deterministic")

    # Device Broker intents (before generic bring-up / status)
    if any(p in t for p in (
        "list broker tools", "device broker tools", "available broker tools",
        "what tools can the device broker",
    )):
        return Intent(kind=IntentKind.DEVICE_LIST_TOOLS, risk_level=RiskLevel.L0, confidence=0.9, notes="deterministic")

    if any(p in t for p in ("execution history", "audit log", "broker audit", "device audit")):
        return Intent(kind=IntentKind.DEVICE_AUDIT, risk_level=RiskLevel.L0, confidence=0.85, notes="deterministic")

    if any(p in t for p in (
        "operating system", "what os", "system info", "platform info",
        "what operating system",
    )):
        return Intent(kind=IntentKind.DEVICE_SYSTEM_INFO, risk_level=RiskLevel.L0, confidence=0.9, notes="deterministic")

    if any(p in t for p in (
        "toolchain", "toolchains", "embedded toolchain", "installed tool",
        "which embedded", "tool versions",
    )):
        return Intent(kind=IntentKind.DEVICE_TOOLCHAINS, risk_level=RiskLevel.L0, confidence=0.9, notes="deterministic")

    if re.search(r"(?i)run (the )?(approved )?version[- ]?check|run (python|git|gcc|cmake|uname).*(version|check)", text):
        return Intent(kind=IntentKind.DEVICE_RUN_COMMAND, risk_level=RiskLevel.L1, confidence=0.9, notes="deterministic")

    if re.search(r"(?i)\bwrite\b.+\bto\b|\bwrite (a )?file\b", text) and "decision" not in t and "note" not in t:
        return Intent(kind=IntentKind.DEVICE_WRITE_FILE, risk_level=RiskLevel.L1, confidence=0.85, notes="deterministic")

    if re.search(r"(?i)\bread (the )?(project )?configuration|\bread (the )?file\b|\bread [\"'\w./~-]+", text):
        return Intent(kind=IntentKind.DEVICE_READ_FILE, risk_level=RiskLevel.L0, confidence=0.85, notes="deterministic")

    if any(p in t for p in (
        "show the files", "list the files", "list files", "files in my",
        "files in the", "workspace files", "list directory", "list the directory",
        "show files in",
    )):
        return Intent(kind=IntentKind.DEVICE_LIST_DIR, risk_level=RiskLevel.L0, confidence=0.9, notes="deterministic")

    if re.search(r"(?i)\bfile info\b|\bstat\b .+", text):
        return Intent(kind=IntentKind.DEVICE_FILE_INFO, risk_level=RiskLevel.L0, confidence=0.85, notes="deterministic")

    discovery_keys = (
        "check the devices", "devices connected", "connected devices",
        "hardware discovery", "discover hardware", "enumerate hardware",
        "what boards are connected", "what devices are connected",
        "scan usb", "list connected hardware", "inspect connected hardware",
        "check devices connected", "devices connected to this",
    )
    if any(p in t for p in discovery_keys):
        return Intent(
            kind=IntentKind.HARDWARE_DISCOVERY,
            needs_cloud=False,
            agent_hints=["hardware", "lab", "discovery"],
            risk_level=RiskLevel.L0,
            confidence=0.92,
            notes="deterministic",
        )

    bringup_keys = (
        "bring up", "bring-up", "bringup", "connected board",
        "development board", "flash the board", "probe the board", "identify the board",
        "connected hardware", "discover the connected", "discover connected",
    )
    if any(p in t for p in bringup_keys):
        return Intent(
            kind=IntentKind.HARDWARE_BRINGUP,
            needs_cloud=False,
            agent_hints=["hardware", "lab", "firmware"],
            risk_level=RiskLevel.L0,
            confidence=0.85,
            notes="deterministic",
        )

    if any(p in t for p in ("what can you", "capabilities", "what do you do")):
        return Intent(kind=IntentKind.CAPABILITY_QUERY, confidence=0.8, notes="deterministic")

    if t == "status" or t.endswith(" status") or t.startswith("status "):
        return Intent(kind=IntentKind.STATUS, confidence=0.8, notes="deterministic")

    return Intent(kind=IntentKind.GENERAL, confidence=0.4, notes="deterministic-fallback")


def _intent_from_dict(data: dict[str, Any]) -> Intent:
    kind_raw = str(data.get("kind", "unknown")).strip().lower()
    try:
        kind = IntentKind(kind_raw)
    except ValueError:
        kind = IntentKind.UNKNOWN

    risk_raw = str(data.get("risk_level", "L0")).strip().upper()
    try:
        risk = RiskLevel(risk_raw)
    except ValueError:
        risk = RiskLevel.L0

    hints = data.get("agent_hints") or []
    if not isinstance(hints, list):
        hints = []

    conf = data.get("confidence", 0.5)
    try:
        conf_f = float(conf)
    except (TypeError, ValueError):
        conf_f = 0.5

    return Intent(
        kind=kind,
        project_ref=data.get("project_ref"),
        needs_cloud=bool(data.get("needs_cloud", False)),
        agent_hints=[str(h) for h in hints],
        risk_level=risk,
        confidence=max(0.0, min(1.0, conf_f)),
        notes=str(data.get("notes") or "ollama"),
    )


class ModelGateway:
    def __init__(self, settings=SETTINGS):
        self.settings = settings

    def ollama_reachable(self) -> bool:
        try:
            with httpx.Client(timeout=2.0) as client:
                r = client.get(f"{self.settings.ollama_host.rstrip('/')}/api/tags")
                return r.status_code == 200
        except Exception:
            return False

    def classify_intent(self, text: str) -> tuple[Intent, str]:
        quick = deterministic_intent(text)
        if quick.kind not in (IntentKind.GENERAL, IntentKind.UNKNOWN) and quick.confidence >= 0.75:
            return quick, "deterministic"

        if not self.ollama_reachable():
            return quick, "deterministic"

        payload = {
            "model": self.settings.ollama_model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1, "num_ctx": 2048},
            "messages": [
                {"role": "system", "content": _INTENT_SYSTEM},
                {"role": "user", "content": text},
            ],
        }
        try:
            with httpx.Client(timeout=self.settings.request_timeout_s) as client:
                r = client.post(
                    f"{self.settings.ollama_host.rstrip('/')}/api/chat",
                    json=payload,
                )
                r.raise_for_status()
                body = r.json()
            content = (body.get("message") or {}).get("content") or ""
            data = _extract_json(content)
            if not data:
                log.warning("Ollama intent JSON parse failed; using deterministic")
                return quick, "deterministic"
            return _intent_from_dict(data), "ollama"
        except Exception as exc:
            log.warning("Ollama intent failed: %s", exc)
            return quick, "deterministic"
