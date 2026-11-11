"""Lazy EngineeringOS singleton bound to trusted Engineering Broker client."""

from __future__ import annotations

from typing import Optional

from engineering_os import EngineeringOS

from .broker_service import get_engineering_broker_client

_INSTANCE: Optional[EngineeringOS] = None


def get_engineering_os() -> EngineeringOS:
    """Always bind to the trusted Engineering OS Broker client (L2 session)."""
    global _INSTANCE
    client = get_engineering_broker_client()
    if _INSTANCE is None or _INSTANCE.client is not client:
        _INSTANCE = EngineeringOS(client)
    return _INSTANCE


def reset_engineering_os() -> EngineeringOS:
    global _INSTANCE
    _INSTANCE = EngineeringOS(get_engineering_broker_client())
    return _INSTANCE
