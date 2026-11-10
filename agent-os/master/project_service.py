"""Lazy ProjectOS singleton bound to SETTINGS.work_root."""

from __future__ import annotations

from typing import Optional

from project_os import ProjectOS

from .config import SETTINGS

_INSTANCE: Optional[ProjectOS] = None


def get_project_os() -> ProjectOS:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = ProjectOS(SETTINGS.work_root)
    return _INSTANCE


def reset_project_os(work_root=None) -> ProjectOS:
    """Used by tests to point at a temporary work root."""
    global _INSTANCE
    if _INSTANCE is not None:
        try:
            _INSTANCE.close()
        except Exception:
            pass
    root = work_root if work_root is not None else SETTINGS.work_root
    _INSTANCE = ProjectOS(root)
    return _INSTANCE
