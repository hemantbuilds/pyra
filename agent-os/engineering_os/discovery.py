"""Hardware discovery orchestration — all host access via Device Broker."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from device_broker.client import BrokerClient
from device_broker.types import CallContext

from .identify import identify_all
from .toolchain import assess_toolchain


def _call(client: BrokerClient, tool: str, project_id: Optional[str] = None) -> dict[str, Any]:
    result = client.call(
        tool,
        {},
        principal="engineering_os",
        max_level="L0",
        project_id=project_id,
        client="engineering_os",
    )
    if not result.ok:
        return {"ok": False, "error": result.error, "tool": tool, "data": {}}
    return {"ok": True, "tool": tool, "data": result.data, "operation_id": result.operation_id}


def collect_evidence(
    client: BrokerClient,
    *,
    project_id: Optional[str] = None,
) -> dict[str, Any]:
    """Fresh evidence collection — never reuses a previous session's device list."""
    usb = _call(client, "enumerate_usb_devices", project_id)
    serial = _call(client, "enumerate_serial_devices", project_id)
    probes = _call(client, "enumerate_debug_probes", project_id)
    host = _call(client, "get_system_info", project_id)
    platform = _call(client, "get_platform_info", project_id)
    toolchains = _call(client, "get_available_toolchains", project_id)

    errors = [
        x for x in (usb, serial, probes, host, platform, toolchains)
        if not x.get("ok")
    ]

    usb_devices = list((usb.get("data") or {}).get("devices") or [])
    serial_devices = list((serial.get("data") or {}).get("devices") or [])

    # Disconnection / empty handling
    still_present = {
        "usb_count": len(usb_devices),
        "serial_count": len(serial_devices),
        "serial_paths": [d.get("path") for d in serial_devices],
    }

    identifications = identify_all(usb_devices=usb_devices, serial_devices=serial_devices)
    assessment = assess_toolchain(
        host_info=(host.get("data") or {}),
        toolchains=(toolchains.get("data") or {}),
        probe_tools=(probes.get("data") or {}),
        identifications=identifications,
    )

    return {
        "collected_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "project_id": project_id,
        "host": host.get("data") or {},
        "platform": platform.get("data") or {},
        "usb": usb.get("data") or {},
        "serial": serial.get("data") or {},
        "debug_probes": probes.get("data") or {},
        "toolchains_raw": toolchains.get("data") or {},
        "identifications": identifications,
        "toolchain_assessment": assessment,
        "presence": still_present,
        "broker_errors": errors,
        "broker_ops": [x.get("operation_id") for x in (usb, serial, probes, host) if x.get("operation_id")],
    }
