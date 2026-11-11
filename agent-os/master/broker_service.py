"""Lazy DeviceBroker singleton bound to SETTINGS.work_root + Project OS."""

from __future__ import annotations

from typing import Optional

from device_broker import DeviceBroker
from device_broker.client import BrokerClient
from device_broker.policy import BrokerPolicy

from .config import SETTINGS

_BROKER: Optional[DeviceBroker] = None
_CLIENT: Optional[BrokerClient] = None
_ENG_CLIENT: Optional[BrokerClient] = None


def get_broker() -> DeviceBroker:
    global _BROKER, _CLIENT, _ENG_CLIENT
    if _BROKER is None:
        from .project_service import get_project_os

        policy = BrokerPolicy(work_root=SETTINGS.work_root)
        pos = get_project_os()

        def _resolve():
            return pos.active_project()

        _BROKER = DeviceBroker(policy, project_resolver=_resolve)
        _CLIENT = BrokerClient(_BROKER)  # untrusted — no L2 session
        _ENG_CLIENT = _BROKER.create_engineering_client()
    return _BROKER


def get_broker_client() -> BrokerClient:
    """Shared Master/agent client — L0/L1 only (no L2 session)."""
    get_broker()
    assert _CLIENT is not None
    return _CLIENT


def get_engineering_broker_client() -> BrokerClient:
    """Trusted Engineering OS client with explicit L2 tool grants."""
    get_broker()
    assert _ENG_CLIENT is not None
    return _ENG_CLIENT


def reset_broker(work_root=None, project_resolver=None) -> DeviceBroker:
    """Tests: point broker at a temporary work root."""
    global _BROKER, _CLIENT, _ENG_CLIENT
    if _BROKER is not None:
        try:
            _BROKER.close()
        except Exception:
            pass
    root = work_root if work_root is not None else SETTINGS.work_root
    policy = BrokerPolicy(work_root=root)
    if project_resolver is None:
        from .project_service import get_project_os

        pos = get_project_os()

        def project_resolver():
            return pos.active_project()

    _BROKER = DeviceBroker(policy, project_resolver=project_resolver)
    _CLIENT = BrokerClient(_BROKER)
    _ENG_CLIENT = _BROKER.create_engineering_client()
    return _BROKER
