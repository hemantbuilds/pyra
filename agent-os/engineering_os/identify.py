"""Evidence-based hardware identification with explicit confidence levels."""

from __future__ import annotations

from typing import Any, Optional

from .platforms.profiles import match_profiles

# Caps: USB VID/PID alone never yields "confirmed" for MCU silicon.
CONFIDENCE_ORDER = ("unknown", "possible", "probable", "confirmed")


def _cap_confidence(hint: str, *, category: str, reasons: list[str]) -> str:
    """Apply conservative caps so we do not over-claim MCU identity."""
    conf = hint if hint in CONFIDENCE_ORDER else "unknown"
    has_full_usb = any(r.startswith("usb_id:") for r in reasons)
    if category == "debug_probe" and has_full_usb:
        return "confirmed" if conf in ("probable", "confirmed") else conf
    if category == "usb_serial_adapter" and has_full_usb:
        # Adapter identity can be confirmed; MCU remains unknown.
        return "confirmed" if conf in ("probable", "confirmed") else conf
    if category == "development_board":
        # Board family may be probable from VID/PID; MCU not confirmed from USB alone.
        if conf == "confirmed":
            return "probable"
        return conf
    return conf if conf != "confirmed" or has_full_usb else "probable"


def identify_device(device: dict[str, Any], *, source: str) -> dict[str, Any]:
    """
    Identify a single enumerated device.

    Returns structured identification with confidence and unresolved fields.
    """
    vid = device.get("vid")
    pid = device.get("pid")
    manufacturer = device.get("manufacturer")
    product = device.get("product")
    path = device.get("path") or device.get("sysfs_path")

    matches = match_profiles(
        vid=vid, pid=pid, manufacturer=manufacturer, product=product,
    )
    unresolved: list[str] = []
    if not vid or not pid:
        unresolved.append("USB VID/PID unavailable")
    if not manufacturer:
        unresolved.append("USB manufacturer string unavailable")
    if not product:
        unresolved.append("USB product string unavailable")

    if not matches:
        return {
            "device_ref": path,
            "source": source,
            "device_category": "unknown",
            "candidate_manufacturer": manufacturer,
            "candidate_board_family": None,
            "candidate_mcu_family": None,
            "confidence": "unknown",
            "candidates": [],
            "supporting_evidence": _evidence(device, source),
            "unresolved": unresolved or ["No matching platform profile"],
            "notes": (
                "Insufficient evidence to identify board/MCU family. "
                "Provide board marking, datasheet, or probe target info in a later phase."
            ),
        }

    top = matches[0]
    confidence = _cap_confidence(
        top["confidence_hint"], category=top["category"], reasons=top["reasons"],
    )
    if top["category"] == "development_board":
        unresolved.append(
            "MCU silicon not confirmed from USB evidence alone "
            "(bridge/probe IC may differ from target MCU)"
        )
    if top["category"] == "usb_serial_adapter":
        unresolved.append("Serial adapter does not identify a connected MCU")

    return {
        "device_ref": path,
        "source": source,
        "device_category": top["category"],
        "candidate_manufacturer": top["manufacturer"],
        "candidate_board_family": top["board_family"],
        "candidate_mcu_family": top["mcu_family"],
        "confidence": confidence,
        "candidates": matches[:5],
        "supporting_evidence": _evidence(device, source) + [
            {"type": "profile_match", "profile_id": top["profile_id"], "reasons": top["reasons"]},
        ],
        "unresolved": unresolved,
        "notes": top.get("notes") or "",
    }


def identify_all(
    *,
    usb_devices: list[dict[str, Any]],
    serial_devices: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Identify each device independently; never collapse to a single guess."""
    results = []
    seen_keys: set[str] = set()

    for s in serial_devices:
        key = f"serial:{(s.get('vid'), s.get('pid'), s.get('path'))}"
        seen_keys.add(key)
        results.append(identify_device(s, source="serial"))

    for u in usb_devices:
        key = f"usb:{(u.get('vid'), u.get('pid'), u.get('sysfs_path'))}"
        # Skip USB parents already covered by a serial node with same vid/pid+serial
        serial_overlap = any(
            (s.get("vid") == u.get("vid") and s.get("pid") == u.get("pid") and s.get("vid"))
            for s in serial_devices
        )
        if serial_overlap:
            # Still report USB-only devices that are probes without serial nodes later
            if u.get("bDeviceClass") == "09":  # hub
                continue
            # Prefer serial-centric identification when a tty exists for same VID/PID
            continue
        results.append(identify_device(u, source="usb"))

    return results


def _evidence(device: dict[str, Any], source: str) -> list[dict[str, Any]]:
    keys = ("vid", "pid", "manufacturer", "product", "serial", "path", "sysfs_path")
    ev = [{"type": "field", "source": source, "key": k, "value": device.get(k)}
          for k in keys if device.get(k) not in (None, "")]
    return ev
