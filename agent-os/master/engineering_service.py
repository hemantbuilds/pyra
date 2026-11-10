"""Lazy EngineeringOS singleton bound to Device Broker + Project OS."""

from __future__ import annotations

from typing import Optional

from engineering_os import EngineeringOS

from .broker_service import get_broker_client

_INSTANCE: Optional[EngineeringOS] = None


def get_engineering_os() -> EngineeringOS:
    """Always bind to the current Broker client (tests may reset the broker)."""
    global _INSTANCE
    client = get_broker_client()
    if _INSTANCE is None or _INSTANCE.client is not client:
        _INSTANCE = EngineeringOS(client)
    return _INSTANCE


def reset_engineering_os() -> EngineeringOS:
    global _INSTANCE
    _INSTANCE = EngineeringOS(get_broker_client())
    return _INSTANCE
