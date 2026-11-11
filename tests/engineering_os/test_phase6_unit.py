"""Phase 6 unit tests — board ID, build env, firmware prep, command validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from engineering_os.board_id import resolve_board_identification, validated_zephyr_boards
from engineering_os.build_env import (
    assess_build_compatibility,
    discover_build_tools,
    inspect_project_build_system,
)
from engineering_os.firmware_prep import blinky_file_set
from engineering_os.platforms.profiles import match_profiles
from engineering_os import states


def test_imxrt1170_profile_match_with_mculink():
    hits = match_profiles(
        vid="1fc9",
        pid="0143",
        manufacturer="NXP",
        product="MCU-Link CMSIS-DAP",
    )
    assert hits
    ids = [h["profile_id"] for h in hits]
    assert "imxrt1170_evkb" in ids
    top = next(h for h in hits if h["profile_id"] == "imxrt1170_evkb")
    assert top["zephyr_board"]
    assert top["zephyr_board"] in validated_zephyr_boards()


def test_unknown_usb_device():
    board = resolve_board_identification(
        usb_devices=[{"vid": "ffff", "pid": "eeee", "product": "Mystery"}],
        serial_devices=[],
    )
    assert board["identified"] is False
    assert board["board_id"] is None
    assert board["confidence"] == "unknown"


def test_no_connected_hardware():
    board = resolve_board_identification(usb_devices=[], serial_devices=[])
    assert board["identified"] is False
    assert "No connected" in board["unknowns"][0]


def test_missing_manufacturer_product_still_can_match_vid_pid():
    board = resolve_board_identification(
        usb_devices=[{"vid": "1fc9", "pid": "0143", "product": "MCU-Link"}],
        serial_devices=[],
    )
    # May be identified or ambiguous depending on competing profiles
    assert "candidate_boards" in board
    assert board["evidence"]


def test_multiple_candidate_boards_ambiguous():
    # Same VID/PID without distinguishing product → likely ambiguous NXP profiles
    board = resolve_board_identification(
        usb_devices=[{"vid": "1fc9", "pid": "0143"}],
        serial_devices=[],
    )
    if len(board["candidate_boards"]) > 1:
        assert board["identified"] is False


def test_conflicting_board_evidence_lists_candidates():
    board = resolve_board_identification(
        usb_devices=[
            {"vid": "0483", "pid": "374b", "product": "STM32 STLink"},
            {"vid": "1fc9", "pid": "0143", "product": "MCU-Link"},
        ],
        serial_devices=[],
    )
    assert len(board["candidate_boards"]) >= 2


def test_blinky_files_deterministic():
    a = blinky_file_set(board_id="imxrt1170_evkb", zephyr_board="mimxrt1170_evk@B/mimxrt1176/cm7")
    b = blinky_file_set(board_id="imxrt1170_evkb", zephyr_board="mimxrt1170_evk@B/mimxrt1176/cm7")
    assert a == b
    assert "src/main.c" in a
    assert "CMakeLists.txt" in a
    assert "prj.conf" in a


def test_build_tools_missing_and_present():
    def which(name):
        return "/fake/west" if name == "west" else None

    tools = discover_build_tools(which=which)
    assert tools["by_id"]["west"]["available"] is True
    assert tools["by_id"]["cmake"]["available"] is False
    assert "cmake" in tools["missing"]


def test_build_tools_version_failure():
    def which(name):
        return f"/bin/{name}"

    def runner(argv):
        raise RuntimeError("boom")

    tools = discover_build_tools(which=which, version_runner=runner)
    assert tools["by_id"]["west"]["validation"] == "version_failed"


def test_zephyr_ready_and_compat(tmp_path):
    def which(name):
        return {
            "west": "/w",
            "cmake": "/c",
            "ninja": "/n",
            "arm-none-eabi-gcc": "/a",
            "git": "/g",
            "python3": "/p",
        }.get(name)

    tools = discover_build_tools(which=which)
    assert tools["zephyr_ready"] is True
    (tmp_path / "CMakeLists.txt").write_text("x")
    (tmp_path / "prj.conf").write_text("y")
    markers = inspect_project_build_system(tmp_path)
    assert "zephyr" in markers["detected_build_systems"]
    assert markers["buildable_claim"] is False
    compat = assess_build_compatibility(
        tools=tools,
        board_id="imxrt1170_evkb",
        zephyr_board="mimxrt1170_evk@B/mimxrt1176/cm7",
        project_markers=markers,
    )
    assert compat["ready_to_build"] is True


def test_platformio_missing_cli(tmp_path):
    (tmp_path / "platformio.ini").write_text("[env]\n")
    markers = inspect_project_build_system(tmp_path)
    tools = discover_build_tools(which=lambda n: None)
    compat = assess_build_compatibility(
        tools=tools, board_id=None, zephyr_board=None, project_markers=markers,
    )
    assert "platformio" in compat["incompatible_or_incomplete"]


def test_states_constants():
    assert states.BUILT == "built"
    assert states.VERIFIED == "verified"
    assert states.BLOCKED in states.ALLOWED_STATUSES
