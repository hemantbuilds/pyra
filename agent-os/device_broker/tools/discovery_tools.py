"""L0 hardware discovery tools — read-only, no device I/O."""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from ..permissions import PermissionLevel
from .registry import ToolRegistry, ToolSpec

if TYPE_CHECKING:
    from ..broker import DeviceBroker

_SYS_USB = Path("/sys/bus/usb/devices")
_SERIAL_GLOBS = ("ttyACM*", "ttyUSB*", "ttyAMA*")


def register(reg: ToolRegistry, broker: "DeviceBroker") -> None:
    reg.register(ToolSpec(
        name="enumerate_usb_devices",
        description="Enumerate USB devices via sysfs (and optional lsusb). Level 0, read-only.",
        level=PermissionLevel.L0,
        category="discovery",
        handler=lambda **kw: enumerate_usb_devices(broker, **kw),
        input_schema={"type": "object", "properties": {}},
    ))
    reg.register(ToolSpec(
        name="enumerate_serial_devices",
        description="Enumerate serial device nodes with USB/udev metadata. No port open. Level 0.",
        level=PermissionLevel.L0,
        category="discovery",
        handler=lambda **kw: enumerate_serial_devices(broker, **kw),
        input_schema={"type": "object", "properties": {}},
    ))
    reg.register(ToolSpec(
        name="enumerate_debug_probes",
        description="Discover installed debug/programming probe utilities (read-only). Level 0.",
        level=PermissionLevel.L0,
        category="discovery",
        handler=lambda **kw: enumerate_debug_probes(broker, **kw),
        input_schema={"type": "object", "properties": {}},
    ))


def _read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


def _sysfs_usb_device(dev_path: Path) -> Optional[dict[str, Any]]:
    """Parse a /sys/bus/usb/devices/<bus>-<port> directory."""
    vid = _read_text(dev_path / "idVendor")
    pid = _read_text(dev_path / "idProduct")
    if not vid or not pid:
        return None  # interface node or root hub without ids
    return {
        "sysfs_path": str(dev_path),
        "busnum": _read_text(dev_path / "busnum"),
        "devnum": _read_text(dev_path / "devnum"),
        "vid": vid.lower(),
        "pid": pid.lower(),
        "manufacturer": _read_text(dev_path / "manufacturer"),
        "product": _read_text(dev_path / "product"),
        "serial": _read_text(dev_path / "serial"),
        "bDeviceClass": _read_text(dev_path / "bDeviceClass"),
        "bNumInterfaces": _read_text(dev_path / "bNumInterfaces"),
        "speed": _read_text(dev_path / "speed"),
        "devpath": _read_text(dev_path / "devpath"),
    }


def enumerate_usb_devices(broker: "DeviceBroker", **_: Any) -> dict[str, Any]:
    devices: list[dict[str, Any]] = []
    source = "sysfs"
    if _SYS_USB.exists():
        for child in sorted(_SYS_USB.iterdir()):
            name = child.name
            # Device nodes look like 1-2 or 1-2.3 — skip interfaces (1-2:1.0) and usbN roots optionally
            if ":" in name:
                continue
            if name.startswith("usb"):
                continue
            info = _sysfs_usb_device(child)
            if info:
                devices.append(info)

    lsusb_text = None
    try:
        data = broker._run_command_impl(["lsusb"], cwd=None, level_override="L0")  # noqa: SLF001
        lsusb_text = data.get("stdout") or ""
    except Exception as exc:  # noqa: BLE001
        lsusb_text = f"(lsusb unavailable: {exc})"

    return {
        "devices": devices,
        "count": len(devices),
        "source": source,
        "lsusb": lsusb_text,
        "note": "Read-only USB enumeration. No device claims made here.",
    }


def _udev_properties(broker: "DeviceBroker", node: str) -> dict[str, str]:
    """Run allowlisted udevadm info for a validated /dev node."""
    path = Path(node)
    if not _is_allowed_serial_node(path):
        return {}
    try:
        data = broker._run_command_impl(  # noqa: SLF001
            ["udevadm", "info", "--query=property", f"--name={path}"],
            cwd=None,
            level_override="L0",
        )
        props: dict[str, str] = {}
        for line in (data.get("stdout") or "").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                props[k] = v
        return props
    except Exception:
        return {}


def _is_allowed_serial_node(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    name = resolved.name
    if not (name.startswith("ttyACM") or name.startswith("ttyUSB") or name.startswith("ttyAMA")):
        # allow /dev/serial/by-id/* after resolve to tty*
        if "serial" in str(resolved):
            return name.startswith("tty")
        return False
    return str(resolved).startswith("/dev/")


def _serial_sysfs_usb(path: Path) -> dict[str, Any]:
    """Follow /sys/class/tty/<name>/device to USB parent attrs."""
    out: dict[str, Any] = {}
    tty_sys = Path("/sys/class/tty") / path.name
    if not tty_sys.exists():
        return out
    try:
        device = (tty_sys / "device").resolve()
    except OSError:
        return out
    # Walk up looking for idVendor
    cur = device
    for _ in range(8):
        if (cur / "idVendor").exists():
            info = _sysfs_usb_device(cur)
            if info:
                return info
        if cur.parent == cur:
            break
        cur = cur.parent
    return out


def enumerate_serial_devices(broker: "DeviceBroker", **_: Any) -> dict[str, Any]:
    nodes: list[Path] = []
    for pattern in _SERIAL_GLOBS:
        nodes.extend(Path("/dev").glob(pattern))
    by_id_dir = Path("/dev/serial/by-id")
    by_id_links = list(by_id_dir.glob("*")) if by_id_dir.exists() else []

    devices = []
    for node in sorted(set(nodes), key=lambda p: p.name):
        try:
            st = node.lstat()
            mode = oct(st.st_mode & 0o777)
            readable = os.access(node, os.R_OK)
            writable = os.access(node, os.W_OK)
        except OSError:
            mode, readable, writable = None, False, False
        usb = _serial_sysfs_usb(node)
        udev = _udev_properties(broker, str(node))
        devices.append({
            "path": str(node),
            "exists": node.exists(),
            "permissions": mode,
            "readable": readable,
            "writable_by_user": writable,
            "vid": usb.get("vid") or _vid_from_udev(udev),
            "pid": usb.get("pid") or _pid_from_udev(udev),
            "manufacturer": usb.get("manufacturer") or udev.get("ID_VENDOR_FROM_DATABASE") or udev.get("ID_VENDOR"),
            "product": usb.get("product") or udev.get("ID_MODEL_FROM_DATABASE") or udev.get("ID_MODEL"),
            "serial": usb.get("serial") or udev.get("ID_SERIAL_SHORT") or udev.get("ID_SERIAL"),
            "usb_interface": udev.get("ID_USB_INTERFACE_NUM"),
            "sysfs_usb": usb or None,
            "udev": {k: udev[k] for k in (
                "ID_VENDOR_ID", "ID_MODEL_ID", "ID_USB_DRIVER", "ID_SERIAL",
                "DEVPATH", "ID_BUS",
            ) if k in udev},
            "note": "Node enumerated only; serial port was not opened.",
        })

    by_id = []
    for link in sorted(by_id_links, key=lambda p: p.name):
        try:
            by_id.append({"path": str(link), "resolved": str(link.resolve()), "is_symlink": link.is_symlink()})
        except OSError:
            by_id.append({"path": str(link), "error": "resolve_failed"})

    return {
        "devices": devices,
        "count": len(devices),
        "by_id": by_id,
        "note": "Read-only serial enumeration. Not every serial device is an MCU.",
    }


def _vid_from_udev(udev: dict[str, str]) -> Optional[str]:
    v = udev.get("ID_VENDOR_ID")
    return v.lower() if v else None


def _pid_from_udev(udev: dict[str, str]) -> Optional[str]:
    v = udev.get("ID_MODEL_ID")
    return v.lower() if v else None


def enumerate_debug_probes(broker: "DeviceBroker", **_: Any) -> dict[str, Any]:
    """Presence/version of probe tools — no target connect/reset/flash."""
    probes = [
        ("openocd", ["openocd", "--version"]),
        ("probe-rs", ["probe-rs", "--version"]),
        ("pyocd", ["pyocd", "--version"]),
        ("JLinkExe", ["JLinkExe", "-?"]),
        ("STM32_Programmer_CLI", ["STM32_Programmer_CLI", "--version"]),
        ("esptool.py", ["esptool.py", "version"]),
    ]
    found = []
    missing = []
    for name, argv in probes:
        which = None
        try:
            w = broker._run_command_impl(["which", argv[0]], cwd=None, level_override="L0")  # noqa: SLF001
            which = (w.get("stdout") or "").strip() or None
        except Exception:
            which = None
        if not which:
            missing.append(name)
            continue
        version = None
        error = None
        try:
            # JLinkExe -? may return non-zero; still capture output
            data = broker._run_command_impl(argv, cwd=None, level_override="L0")  # noqa: SLF001
            version = ((data.get("stdout") or "") + (data.get("stderr") or ""))[:500].strip()
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
        found.append({
            "name": name,
            "path": which,
            "version_output": version,
            "error": error,
            "note": "Tool presence only; no target session started.",
        })
    return {"found": found, "missing": missing, "count_found": len(found)}
