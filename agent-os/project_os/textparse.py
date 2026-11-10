"""Extract project/task phrases from natural-language commands."""

from __future__ import annotations

import re
from typing import Optional


def extract_project_name_for_create(text: str) -> Optional[str]:
    t = text.strip()
    patterns = [
        r"(?i)create\s+(?:a\s+)?(?:new\s+)?project\s+(?:called|named)\s+(.+)$",
        r"(?i)create\s+(?:a\s+)?(?:new\s+)?project\s*[:\-]\s*(.+)$",
        r"(?i)(?:new|start)\s+project\s+(?:for|called|named)\s+(.+)$",
        r"(?i)create\s+(?:a\s+)?(?:new\s+)?(.+?)\s+project\.?$",
        r"(?i)create\s+(?:a\s+)?(?:new\s+)?project\s+for\s+(.+)$",
    ]
    for pat in patterns:
        m = re.search(pat, t)
        if m:
            name = _clean_name(m.group(1))
            if name:
                return name
    return None


def extract_project_ref_for_switch(text: str) -> Optional[str]:
    t = text.strip()
    patterns = [
        r"(?i)switch\s+to\s+(?:the\s+)?(.+?)(?:\s+project)?\.?$",
        r"(?i)continue\s+(?:the\s+|my\s+)?(.+?)(?:\s+project)?\.?$",
        r"(?i)resume\s+(?:the\s+|my\s+)?(.+?)(?:\s+project)?\.?$",
        r"(?i)open\s+(?:the\s+)?(.+?)\s+project\.?$",
    ]
    for pat in patterns:
        m = re.search(pat, t)
        if m:
            name = _clean_name(m.group(1))
            # Avoid swallowing generic verbs
            if name and name.lower() not in {"project", "this", "it", "my"}:
                # Strip trailing "project"
                name = re.sub(r"(?i)\s+project$", "", name).strip()
                return name or None
    return None


def extract_task_title(text: str) -> Optional[str]:
    t = text.strip()
    patterns = [
        r"(?i)add\s+(?:a\s+)?task\s+to\s+(.+)$",
        r"(?i)create\s+(?:a\s+)?task\s+(?:to\s+|for\s+)?(.+)$",
        r"(?i)add\s+(?:a\s+)?task[:\-]\s*(.+)$",
        r"(?i)new\s+task[:\-]\s*(.+)$",
    ]
    for pat in patterns:
        m = re.search(pat, t)
        if m:
            title = m.group(1).strip().rstrip(".")
            # "add a task to investigate X" -> "investigate X"
            title = re.sub(r"(?i)^to\s+", "", title).strip()
            return title or None
    return None


def extract_completed_task_ref(text: str) -> Optional[str]:
    t = text.strip()
    patterns = [
        r"(?i)mark\s+(?:the\s+)?(.+?)\s+as\s+completed",
        r"(?i)mark\s+(?:the\s+)?(.+?)\s+complete",
        r"(?i)complete\s+(?:the\s+)?(?:task\s+)?(.+)$",
        r"(?i)finish\s+(?:the\s+)?(?:task\s+)?(.+)$",
    ]
    for pat in patterns:
        m = re.search(pat, t)
        if m:
            return m.group(1).strip().rstrip(".")
    return None


def extract_note_text(text: str) -> Optional[str]:
    t = text.strip()
    patterns = [
        r"(?i)(?:save|add|record)\s+(?:this\s+)?(?:engineering\s+)?decision[:\-]\s*(.+)$",
        r"(?i)(?:save|add|record)\s+(?:a\s+)?(?:note|decision)\s*[:\-]\s*(.+)$",
        r"(?i)(?:save|add|record)\s+(?:this\s+)?(?:note|decision)\s+(.+)$",
        r"(?i)note\s*[:\-]\s*(.+)$",
    ]
    for pat in patterns:
        m = re.search(pat, t)
        if m:
            return m.group(1).strip()
    return None


def is_decision_phrase(text: str) -> bool:
    return bool(re.search(r"(?i)\bdecision\b", text))


def _clean_name(raw: str) -> str:
    name = raw.strip().strip("\"'`").rstrip(".")
    name = re.sub(r"(?i)^(a|an|the)\s+", "", name).strip()
    return name
