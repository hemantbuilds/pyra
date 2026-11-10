"""Policy: approved roots, command allowlist, resource limits."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class CommandSpec:
    """Exact argv prefix allowlist entry (no shell)."""

    name: str
    argv_prefix: tuple[str, ...]
    description: str = ""
    level: str = "L1"
    # If True, only these exact argv lengths are allowed (prefix + fixed).
    max_args: int = 8


# Version / discovery commands (also used by sysinfo probes).
DEFAULT_COMMANDS: list[CommandSpec] = [
    CommandSpec("uname", ("uname", "-a"), "kernel/platform", level="L0"),
    CommandSpec("python_version", ("python3", "--version"), "Python version", level="L0"),
    CommandSpec("which", ("which",), "locate binary", level="L0", max_args=2),
    CommandSpec("git_version", ("git", "--version"), "git version", level="L0"),
    CommandSpec("cmake_version", ("cmake", "--version"), "cmake version", level="L0"),
    CommandSpec("gcc_version", ("gcc", "--version"), "gcc version", level="L0"),
    CommandSpec("arm_gcc_version", ("arm-none-eabi-gcc", "--version"), "ARM GCC", level="L0"),
    CommandSpec("esptool_version", ("esptool.py", "version"), "esptool", level="L0"),
    CommandSpec("probe_rs_version", ("probe-rs", "--version"), "probe-rs", level="L0"),
    CommandSpec("openocd_version", ("openocd", "--version"), "openocd", level="L0"),
    CommandSpec("lsusb", ("lsusb",), "USB device list", level="L0", max_args=2),
    CommandSpec("udevadm_info", ("udevadm", "info"), "udev device properties", level="L0", max_args=6),
    CommandSpec("pyocd_version", ("pyocd", "--version"), "pyOCD version", level="L0"),
    CommandSpec("jlink_help", ("JLinkExe", "-?"), "J-Link presence probe", level="L0"),
    CommandSpec("stm32prog_version", ("STM32_Programmer_CLI", "--version"), "STM32CubeProgrammer", level="L0"),
]


@dataclass
class BrokerPolicy:
    work_root: Path
    extra_roots: list[Path] = field(default_factory=list)
    commands: list[CommandSpec] = field(default_factory=lambda: list(DEFAULT_COMMANDS))
    max_read_bytes: int = 512_000
    max_write_bytes: int = 512_000
    max_list_entries: int = 500
    max_command_output_bytes: int = 64_000
    command_timeout_s: float = 15.0
    default_max_level: str = "L1"

    def global_root(self) -> Path:
        return self.work_root / "global"

    def projects_root(self) -> Path:
        return self.work_root / "projects"

    def ensure_base_dirs(self) -> None:
        self.work_root.mkdir(parents=True, exist_ok=True)
        self.global_root().mkdir(parents=True, exist_ok=True)
        self.projects_root().mkdir(parents=True, exist_ok=True)

    def match_command(self, argv: list[str]) -> Optional[CommandSpec]:
        if not argv:
            return None
        for spec in self.commands:
            prefix = list(spec.argv_prefix)
            if argv[: len(prefix)] == prefix:
                extra = len(argv) - len(prefix)
                if extra < 0 or (len(prefix) + extra) > (len(prefix) + max(0, spec.max_args - len(prefix))):
                    # max_args is total argv length budget relative to prefix rules:
                    if len(argv) > spec.max_args:
                        return None
                if len(argv) > spec.max_args:
                    return None
                # Reject shell metacharacters in any arg
                for a in argv:
                    if any(ch in a for ch in ("|", ";", "&", "`", "$", "\n", ">", "<")):
                        return None
                return spec
        return None
