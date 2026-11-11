"""Structured board identification for Phase 6 workflows."""

from __future__ import annotations

from typing import Any, Optional

from .platforms.profiles import PLATFORM_PROFILES, match_profiles


def resolve_board_identification(
    *,
    usb_devices: list[dict[str, Any]],
    serial_devices: list[dict[str, Any]],
    identifications: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Produce a workflow-oriented board identification result.

    Does not invent VID/PID. Prefers development_board candidates with
    zephyr_board metadata when evidence supports them.
    """
    devices = list(serial_devices) + list(usb_devices)
    candidates: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    unknowns: list[str] = []

    if not devices:
        return {
            "identified": False,
            "board_id": None,
            "board_name": None,
            "mcu_family": None,
            "mcu_model": None,
            "zephyr_board": None,
            "confidence": "unknown",
            "evidence": [],
            "unknowns": ["No connected USB/serial devices enumerated"],
            "candidate_boards": [],
        }

    seen: set[str] = set()
    for d in devices:
        hits = match_profiles(
            vid=d.get("vid"),
            pid=d.get("pid"),
            manufacturer=d.get("manufacturer"),
            product=d.get("product"),
        )
        for h in hits:
            if h["category"] != "development_board":
                continue
            pid = h["profile_id"]
            if pid in seen:
                continue
            seen.add(pid)
            candidates.append(h)
            evidence.append(
                {
                    "type": "profile_match",
                    "profile_id": pid,
                    "reasons": h.get("reasons"),
                    "device_ref": d.get("path") or d.get("sysfs_path"),
                    "vid": d.get("vid"),
                    "pid": d.get("pid"),
                    "product": d.get("product"),
                }
            )

    if not candidates:
        unknowns.append("No development_board profile matched enumerated devices")
        return {
            "identified": False,
            "board_id": None,
            "board_name": None,
            "mcu_family": None,
            "mcu_model": None,
            "zephyr_board": None,
            "confidence": "unknown",
            "evidence": evidence,
            "unknowns": unknowns,
            "candidate_boards": [],
        }

    # Prefer profiles with an explicit zephyr_board and higher score.
    candidates.sort(
        key=lambda c: (1 if c.get("zephyr_board") else 0, c.get("score") or 0),
        reverse=True,
    )
    top = candidates[0]
    # Multiple strong candidates are ambiguous only when scores are close.
    strong = [c for c in candidates if (c.get("score") or 0) >= 50]
    ambiguous = False
    if len(strong) > 1:
        gap = (strong[0].get("score") or 0) - (strong[1].get("score") or 0)
        if gap < 12:
            ambiguous = True

    confidence = top.get("confidence_hint") or "possible"
    if confidence == "confirmed":
        confidence = "probable"  # board MCU still not silicon-confirmed

    identified = (not ambiguous) and confidence in ("probable", "confirmed") and bool(
        top.get("profile_id")
    )
    if ambiguous:
        unknowns.append("Multiple candidate board profiles matched — ambiguous")
        identified = False

    unknowns.append(
        "MCU silicon not confirmed from USB evidence alone"
    )

    return {
        "identified": identified,
        "board_id": top["profile_id"] if identified else None,
        "board_name": top.get("board_name") if identified else None,
        "mcu_family": top.get("mcu_family") if identified else None,
        "mcu_model": top.get("mcu_model") if identified else None,
        "zephyr_board": top.get("zephyr_board") if identified else None,
        "confidence": confidence if identified else ("possible" if candidates else "unknown"),
        "evidence": evidence,
        "unknowns": unknowns,
        "candidate_boards": [
            {
                "board_id": c["profile_id"],
                "board_name": c.get("board_name"),
                "score": c.get("score"),
                "zephyr_board": c.get("zephyr_board"),
                "reasons": c.get("reasons"),
            }
            for c in candidates[:8]
        ],
    }


def profile_by_id(board_id: str) -> Optional[dict[str, Any]]:
    for p in PLATFORM_PROFILES:
        if p.id == board_id:
            return {
                "board_id": p.id,
                "board_name": p.board_name or p.board_family,
                "mcu_family": p.mcu_family,
                "mcu_model": p.mcu_model,
                "zephyr_board": p.zephyr_board,
                "build_systems": list(p.build_systems),
            }
    return None


def validated_zephyr_boards() -> set[str]:
    return {p.zephyr_board for p in PLATFORM_PROFILES if p.zephyr_board}
