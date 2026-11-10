"""Format structured discovery reports for speech / HUD / artifacts."""

from __future__ import annotations

import json
from typing import Any, Optional


def build_report(evidence: dict[str, Any]) -> dict[str, Any]:
    host = evidence.get("host") or {}
    serial = (evidence.get("serial") or {}).get("devices") or []
    usb = (evidence.get("usb") or {}).get("devices") or []
    probes = evidence.get("debug_probes") or {}
    idents = evidence.get("identifications") or []
    assess = evidence.get("toolchain_assessment") or {}

    text = render_text_report(evidence)
    summary = _speech_summary(evidence)

    structured = {
        "title": "PYRA HARDWARE DISCOVERY REPORT",
        "collected_at": evidence.get("collected_at"),
        "project_id": evidence.get("project_id"),
        "host": {
            "os": host.get("system"),
            "architecture": host.get("machine"),
            "release": host.get("release"),
            "node": host.get("node"),
        },
        "connected_serial_devices": serial,
        "connected_usb_devices": usb,
        "identifications": idents,
        "debug_probes": probes,
        "development_environment": assess.get("components"),
        "overall_readiness": assess.get("overall"),
        "unresolved": _all_unresolved(idents),
        "recommended_next_steps": assess.get("next_steps") or [],
        "broker_errors": evidence.get("broker_errors") or [],
    }
    return {
        "structured": structured,
        "text": text,
        "speech": summary,
        "json": json.dumps(structured, indent=2, ensure_ascii=False),
    }


def render_text_report(evidence: dict[str, Any]) -> str:
    host = evidence.get("host") or {}
    lines = [
        "PYRA HARDWARE DISCOVERY REPORT",
        "",
        "Host:",
        f"  OS: {host.get('system') or '(unavailable)'}",
        f"  Architecture: {host.get('machine') or '(unavailable)'}",
        f"  Release: {host.get('release') or '(unavailable)'}",
        "",
        "Connected serial devices:",
    ]
    serial = (evidence.get("serial") or {}).get("devices") or []
    if not serial:
        lines.append("  (none detected)")
    for i, d in enumerate(serial, 1):
        lines.extend([
            f"Device {i}:",
            f"  Device node: {d.get('path') or '(unavailable)'}",
            f"  USB VID: {d.get('vid') or '(unavailable)'}",
            f"  USB PID: {d.get('pid') or '(unavailable)'}",
            f"  Manufacturer: {d.get('manufacturer') or '(unavailable)'}",
            f"  Product: {d.get('product') or '(unavailable)'}",
            f"  Serial number: {d.get('serial') or '(unavailable)'}",
            "",
        ])

    lines.append("Identification:")
    idents = evidence.get("identifications") or []
    if not idents:
        lines.append("  No devices to identify.")
    for ident in idents:
        lines.extend([
            f"  Device: {ident.get('device_ref')}",
            f"    Category: {ident.get('device_category')}",
            f"    Candidate board: {ident.get('candidate_board_family') or '(unknown)'}",
            f"    Candidate MCU: {ident.get('candidate_mcu_family') or '(unknown)'}",
            f"    Confidence: {ident.get('confidence')}",
        ])
        cands = ident.get("candidates") or []
        if len(cands) > 1:
            lines.append("    Other candidates:")
            for c in cands[1:4]:
                lines.append(
                    f"      - {c.get('board_family')} (score={c.get('score')}, "
                    f"hint={c.get('confidence_hint')})"
                )
        lines.append("")

    probes = evidence.get("debug_probes") or {}
    lines.append("Debug / programming tools on host:")
    found = probes.get("found") or []
    missing = probes.get("missing") or []
    if found:
        for p in found:
            lines.append(f"  - {p.get('name')}: {p.get('path')}")
    else:
        lines.append("  (none found)")
    if missing:
        lines.append(f"  Missing: {', '.join(missing)}")
    lines.append("")

    assess = evidence.get("toolchain_assessment") or {}
    comps = assess.get("components") or {}
    lines.append("Development environment:")
    for key in ("compiler", "build_system", "sdk", "programmer", "debugger"):
        block = comps.get(key) or {}
        status = block.get("status") or "unknown"
        detail = block.get("detail")
        extra = f" ({detail})" if detail else ""
        lines.append(f"  {key}: {status}{extra}")
    lines.append("")
    lines.append(f"Overall readiness: {assess.get('overall') or 'unknown'}")
    lines.append("")
    lines.append("Unresolved information:")
    unresolved = _all_unresolved(idents)
    if not unresolved:
        lines.append("  (none recorded)")
    else:
        for u in unresolved:
            lines.append(f"  - {u}")
    lines.append("")
    lines.append("Recommended next steps:")
    for s in (assess.get("next_steps") or ["(none)"]):
        lines.append(f"  - {s}")
    lines.append("")
    lines.append(
        "Note: Phase 4 is discovery-only. No flash, erase, reset, or serial I/O was performed."
    )
    return "\n".join(lines)


def _speech_summary(evidence: dict[str, Any]) -> str:
    serial_n = (evidence.get("presence") or {}).get("serial_count", 0)
    usb_n = (evidence.get("presence") or {}).get("usb_count", 0)
    idents = evidence.get("identifications") or []
    assess = (evidence.get("toolchain_assessment") or {}).get("overall") or "unknown"
    if serial_n == 0 and not idents:
        return (
            f"Hardware discovery finished. No serial MCU-like devices found "
            f"({usb_n} USB device records). Toolchain readiness: {assess}. "
            "I will not assume a board identity."
        )
    bits = []
    for ident in idents[:3]:
        bits.append(
            f"{ident.get('device_ref')}: {ident.get('candidate_board_family') or 'unknown'} "
            f"({ident.get('confidence')})"
        )
    more = f" and {len(idents) - 3} more" if len(idents) > 3 else ""
    return (
        f"Hardware discovery finished. {serial_n} serial device(s), {usb_n} USB record(s). "
        f"Identities: {'; '.join(bits)}{more}. "
        f"Overall readiness: {assess}. Discovery only — no flashing."
    )


def _all_unresolved(idents: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for ident in idents:
        for u in ident.get("unresolved") or []:
            if u not in out:
                out.append(u)
    return out
