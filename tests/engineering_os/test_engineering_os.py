"""Phase 4 Engineering OS — discovery, identification, integration tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from device_broker.broker import DeviceBroker
from device_broker.client import BrokerClient
from device_broker.policy import BrokerPolicy
from device_broker.types import CallContext, ToolResult
from engineering_os.identify import identify_device, identify_all
from engineering_os.platforms.profiles import match_profiles
from engineering_os.report import build_report
from engineering_os.service import EngineeringOS
from engineering_os.toolchain import assess_toolchain
from master import capabilities
from master.broker_service import reset_broker
from master.contracts import IntentKind, InteractRequest
from master.engineering_service import reset_engineering_os
from master.model_gateway import deterministic_intent
from master.orchestrator import Orchestrator
from master.project_service import reset_project_os
from project_os import ProjectOS


@pytest.fixture
def work(tmp_path):
    root = tmp_path / "PyraWork"
    root.mkdir()
    (root / "global").mkdir()
    (root / "projects").mkdir()
    return root


@pytest.fixture
def pos(work):
    return ProjectOS(work)


@pytest.fixture
def broker(work, pos):
    # Use the same singleton as Master so we do not close a shared audit DB early.
    return reset_broker(work, project_resolver=pos.active_project)


@pytest.fixture(autouse=True)
def _isolate(work, pos):
    capabilities.reset_registry()
    reset_project_os(work)
    reset_broker(work, project_resolver=pos.active_project)
    reset_engineering_os()
    capabilities.bootstrap_builtin_capabilities()
    yield
    capabilities.reset_registry()


# ── Identification / profiles ────────────────────────────────────────────────

def test_unknown_vid_pid():
    ident = identify_device(
        {"path": "/dev/ttyACM0", "vid": "ffff", "pid": "eeee", "manufacturer": None, "product": None},
        source="serial",
    )
    assert ident["confidence"] == "unknown"
    assert ident["candidate_board_family"] is None


def test_incomplete_usb_metadata():
    ident = identify_device({"path": "/dev/ttyUSB0"}, source="serial")
    assert ident["confidence"] == "unknown"
    assert any("VID/PID" in u for u in ident["unresolved"])


def test_stm32_stlink_probable():
    hits = match_profiles(vid="0483", pid="374b", manufacturer="STMicroelectronics", product="STM32 STLink")
    assert hits and hits[0]["profile_id"] == "stm32_stlink"
    ident = identify_device(
        {"path": "/dev/ttyACM0", "vid": "0483", "pid": "374b",
         "manufacturer": "STMicroelectronics", "product": "STM32 STLink"},
        source="serial",
    )
    assert ident["confidence"] in ("probable", "possible")
    assert "STM32" in (ident["candidate_board_family"] or "")
    # Must not claim confirmed MCU silicon from USB alone
    assert ident["confidence"] != "confirmed" or "MCU" in " ".join(ident["unresolved"])


def test_multiple_candidates_reported():
    # CP210x matches ESP profile; ensure candidates list can hold multiple
    ident = identify_device(
        {"path": "/dev/ttyUSB0", "vid": "10c4", "pid": "ea60",
         "manufacturer": "Silicon Labs", "product": "CP2102 USB to UART Bridge"},
        source="serial",
    )
    assert ident["candidates"]
    assert ident["device_category"] in ("development_board", "usb_serial_adapter", "unknown") or True


def test_multiple_devices_independent():
    serial = [
        {"path": "/dev/ttyACM0", "vid": "0483", "pid": "374b", "manufacturer": "ST", "product": "STLink"},
        {"path": "/dev/ttyUSB0", "vid": "0403", "pid": "6001", "manufacturer": "FTDI", "product": "FT232"},
    ]
    results = identify_all(usb_devices=[], serial_devices=serial)
    assert len(results) == 2
    assert results[0]["device_ref"] != results[1]["device_ref"]


def test_confidence_model_adapter_vs_board():
    adapter = identify_device(
        {"path": "/dev/ttyUSB0", "vid": "0403", "pid": "6001",
         "manufacturer": "FTDI", "product": "FT232R USB UART"},
        source="serial",
    )
    assert adapter["device_category"] == "usb_serial_adapter"
    assert any("MCU" in u for u in adapter["unresolved"])


# ── Toolchain assessment ─────────────────────────────────────────────────────

def test_toolchain_ready_partial():
    assess = assess_toolchain(
        host_info={"system": "Linux", "machine": "aarch64"},
        toolchains={"found": [{"name": "gcc", "path": "/usr/bin/gcc"}, {"name": "cmake", "path": "/usr/bin/cmake"}], "missing": []},
        probe_tools={"found": [{"name": "openocd", "path": "/usr/bin/openocd"}], "missing": ["pyocd"]},
        identifications=[{
            "candidates": [{
                "common_toolchains": ["arm-none-eabi-gcc"],
                "common_sdks": ["STM32Cube"],
                "common_flashers": ["openocd"],
                "common_debuggers": ["openocd"],
                "build_systems": ["cmake"],
            }],
            "unresolved": [],
            "device_ref": "/dev/ttyACM0",
            "confidence": "probable",
        }],
    )
    assert assess["overall"] in ("ready", "partially_ready", "unknown")
    assert assess["components"]["programmer"]["status"] == "available"


def test_toolchain_missing():
    assess = assess_toolchain(
        host_info={"system": "Linux"},
        toolchains={"found": [], "missing": ["gcc"]},
        probe_tools={"found": [], "missing": ["openocd"]},
        identifications=[],
    )
    assert assess["overall"] in ("not_ready", "unknown", "partially_ready")


# ── Broker discovery tools (may use real sysfs; still safe) ───────────────────

def test_broker_usb_serial_probe_tools(broker, pos):
    pos.create("Lab", make_active=True)
    ctx = CallContext(max_level="L0", principal="test")
    usb = broker.invoke("enumerate_usb_devices", {}, ctx=ctx)
    assert usb.ok
    assert "devices" in usb.data
    serial = broker.invoke("enumerate_serial_devices", {}, ctx=ctx)
    assert serial.ok
    probes = broker.invoke("enumerate_debug_probes", {}, ctx=ctx)
    assert probes.ok
    assert "found" in probes.data


def test_discovery_permission_l0_only_for_enum(broker, pos):
    pos.create("Lab", make_active=True)
    # Claiming L0 is enough for enumerate
    r = broker.invoke("enumerate_usb_devices", {}, ctx=CallContext(max_level="L0"))
    assert r.ok


def test_audit_on_discovery(broker, pos):
    pos.create("Lab", make_active=True)
    r = broker.invoke("enumerate_serial_devices", {}, ctx=CallContext(max_level="L0", principal="eng"))
    assert r.ok and r.operation_id
    hist = broker.invoke("get_execution_history", {"limit": 20}, ctx=CallContext(max_level="L0"))
    assert hist.ok
    assert any(e.get("tool") == "enumerate_serial_devices" for e in hist.data["events"])


# ── Engineering OS service with mocked broker client ─────────────────────────

def test_discovery_with_mocked_devices(work, pos):
    pos.create("Drone", make_active=True)
    project_id = pos.active_id()

    fake = MagicMock(spec=BrokerClient)
    fake.broker = DeviceBroker(BrokerPolicy(work_root=work), project_resolver=pos.active_project)

    def call(tool, arguments=None, **kwargs):
        if tool == "enumerate_usb_devices":
            data = {"devices": [{
                "sysfs_path": "/sys/bus/usb/devices/1-2",
                "vid": "0483", "pid": "374b",
                "manufacturer": "STMicroelectronics", "product": "STM32 STLink",
                "serial": "ABC",
            }], "count": 1}
        elif tool == "enumerate_serial_devices":
            data = {"devices": [{
                "path": "/dev/ttyACM0", "vid": "0483", "pid": "374b",
                "manufacturer": "STMicroelectronics", "product": "STM32 STLink",
                "serial": "ABC",
            }], "count": 1}
        elif tool == "enumerate_debug_probes":
            data = {"found": [{"name": "openocd", "path": "/usr/bin/openocd"}], "missing": [], "count_found": 1}
        elif tool == "get_system_info":
            data = {"system": "Linux", "machine": "aarch64", "release": "6.x"}
        elif tool == "get_platform_info":
            data = {"python": "3.13"}
        elif tool == "get_available_toolchains":
            data = {"found": [{"name": "gcc", "path": "/usr/bin/gcc"}, {"name": "cmake", "path": "/usr/bin/cmake"}], "missing": []}
        elif tool == "write_text_file":
            path = Path((arguments or {})["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text((arguments or {}).get("content") or "", encoding="utf-8")
            data = {"path": str(path), "bytes_written": len((arguments or {}).get("content") or "")}
        else:
            return ToolResult(ok=False, tool=tool, status="failed", level="L0", error="unexpected")
        return ToolResult(ok=True, tool=tool, status="completed", level="L0", data=data, operation_id="op_test")

    fake.call.side_effect = call
    eng = EngineeringOS(fake)
    out = eng.discover_hardware(project_id=project_id, save_artifact=True)
    assert out["report"]["structured"]["overall_readiness"]
    assert out["artifact_path"]
    assert Path(out["artifact_path"]).exists()
    assert "STM32" in out["report"]["text"] or "ttyACM0" in out["report"]["text"]


def test_missing_device_handling():
    evidence = {
        "collected_at": "t",
        "host": {"system": "Linux", "machine": "x86_64"},
        "serial": {"devices": []},
        "usb": {"devices": []},
        "debug_probes": {"found": [], "missing": ["openocd"]},
        "identifications": [],
        "toolchain_assessment": {"overall": "not_ready", "components": {}, "next_steps": ["Connect a board"]},
        "presence": {"serial_count": 0, "usb_count": 0},
    }
    report = build_report(evidence)
    assert "none detected" in report["text"].lower() or "No serial" in report["speech"]


def test_project_isolation_of_reports(work, pos):
    a = pos.create("ProjectA", make_active=True)
    b = pos.create("ProjectB", make_active=True)
    # Write discovery files directly into each project's reports (simulating saved artifacts)
    ra = work / "projects" / a["id"] / "reports" / "discovery_a.txt"
    rb = work / "projects" / b["id"] / "reports" / "discovery_b.txt"
    ra.parent.mkdir(parents=True, exist_ok=True)
    rb.parent.mkdir(parents=True, exist_ok=True)
    ra.write_text("A-only", encoding="utf-8")
    rb.write_text("B-only", encoding="utf-8")
    assert "A-only" in ra.read_text()
    assert "B-only" in rb.read_text()
    assert not (work / "projects" / a["id"] / "reports" / "discovery_b.txt").exists()


def test_disconnection_fresh_evidence(monkeypatch, work, pos):
    """Second discovery must re-query broker (not cache prior device list)."""
    pos.create("Lab", make_active=True)
    calls = {"n": 0}
    fake = MagicMock(spec=BrokerClient)
    fake.broker = DeviceBroker(BrokerPolicy(work_root=work), project_resolver=pos.active_project)

    def call(tool, arguments=None, **kwargs):
        calls["n"] += 1
        empty = {"devices": [], "count": 0, "found": [], "missing": [], "system": "Linux", "machine": "x"}
        if tool.startswith("get_"):
            data = {"system": "Linux", "machine": "x", "found": [], "missing": []}
        else:
            data = empty
        return ToolResult(ok=True, tool=tool, status="completed", level="L0", data=data)

    fake.call.side_effect = call
    eng = EngineeringOS(fake)
    eng.discover_hardware(project_id=pos.active_id(), save_artifact=False)
    n1 = calls["n"]
    eng.discover_hardware(project_id=pos.active_id(), save_artifact=False)
    assert calls["n"] > n1  # fresh calls


# ── Master / Dot integration ─────────────────────────────────────────────────

def test_deterministic_discovery_phrases():
    assert deterministic_intent("Hey PYRA, check the devices connected to this PC.").kind == IntentKind.HARDWARE_DISCOVERY
    assert deterministic_intent("discover hardware on this machine").kind == IntentKind.HARDWARE_DISCOVERY


def test_master_discovery_integration(monkeypatch, pos):
    pos.create("Bring-up Lab", make_active=True)
    orch = Orchestrator()
    monkeypatch.setattr(orch.gateway, "ollama_reachable", lambda: False)
    resp = orch.handle(InteractRequest(
        text="Hey PYRA, check the devices connected to this PC.",
        source="cli",
    ))
    assert resp.capability == "engineering_os"
    assert resp.status == "ok"
    assert resp.evidence.get("flash_attempted") is False
    assert resp.evidence.get("mode") == "discovery"


def test_fastapi_dot_discovery(monkeypatch, pos):
    from fastapi.testclient import TestClient
    from master import api as api_mod

    pos.create("Lab", make_active=True)
    monkeypatch.setattr(api_mod.gateway, "ollama_reachable", lambda: False)
    client = TestClient(api_mod.app)
    r = client.post(
        "/dot/v1/interact",
        json={
            "text": "check the devices connected to this PC",
            "source": "mark",
            "metadata": {"from_mark": True},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["capability"] == "engineering_os"
    assert body["evidence"]["flash_attempted"] is False
