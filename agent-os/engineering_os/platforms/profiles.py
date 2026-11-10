"""
Hardware platform profiles for evidence-based identification.

Profiles are data only — discovery/identification logic lives elsewhere.
No single board is the default. Unknown VID/PID → no forced match.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class PlatformProfile:
    id: str
    manufacturer: str
    board_family: str
    mcu_family: str
    category: str  # development_board|debug_probe|usb_serial_adapter|sbc|unknown
    usb_ids: tuple[tuple[str, str], ...] = ()  # (vid, pid) lowercase hex
    product_substrings: tuple[str, ...] = ()
    manufacturer_substrings: tuple[str, ...] = ()
    common_toolchains: tuple[str, ...] = ()
    common_sdks: tuple[str, ...] = ()
    common_flashers: tuple[str, ...] = ()
    common_debuggers: tuple[str, ...] = ()
    build_systems: tuple[str, ...] = ()
    docs: tuple[str, ...] = ()
    notes: str = ""


PLATFORM_PROFILES: tuple[PlatformProfile, ...] = (
    PlatformProfile(
        id="arduino_uno_r3_like",
        manufacturer="Arduino / ATmega16U2-CDC clones",
        board_family="Arduino Uno-compatible",
        mcu_family="ATmega328P (typical) — not confirmed by USB alone",
        category="development_board",
        usb_ids=(("2341", "0043"), ("2341", "0001"), ("2a03", "0043")),
        product_substrings=("arduino uno", "arduino"),
        manufacturer_substrings=("arduino",),
        common_toolchains=("avr-gcc",),
        common_sdks=("Arduino AVR core",),
        common_flashers=("avrdude",),
        common_debuggers=(),
        build_systems=("arduino-cli", "platformio"),
        docs=("https://docs.arduino.cc/",),
        notes="USB CDC from 16U2/CH340 clones is common; MCU family is probable only.",
    ),
    PlatformProfile(
        id="arduino_cmsis_dap",
        manufacturer="Arduino",
        board_family="Arduino with CMSIS-DAP / native USB",
        mcu_family="SAMD / other (profile match only)",
        category="development_board",
        usb_ids=(("2341", "0057"), ("2341", "8057")),
        product_substrings=("arduino", "cmsis-dap"),
        manufacturer_substrings=("arduino",),
        common_toolchains=("arm-none-eabi-gcc",),
        common_sdks=("Arduino core",),
        common_flashers=("bossac", "openocd", "probe-rs"),
        common_debuggers=("openocd", "probe-rs"),
        build_systems=("arduino-cli", "platformio", "cmake"),
    ),
    PlatformProfile(
        id="esp32_usb_serial",
        manufacturer="Espressif / common ESP USB-UART",
        board_family="ESP32-family development board (USB-UART bridge)",
        mcu_family="ESP32 / ESP32-S2 / ESP32-S3 / ESP32-C3 (unconfirmed)",
        category="development_board",
        usb_ids=(
            ("10c4", "ea60"),  # CP210x often on ESP boards
            ("1a86", "7523"),  # CH340
            ("1a86", "55d4"),  # CH9102
            ("303a", "1001"),  # Espressif USB-JTAG/serial
            ("303a", "0002"),
        ),
        product_substrings=("cp210", "ch340", "usb jtag", "esp32", "uart"),
        manufacturer_substrings=("silicon labs", "espressif", "qinHeng".lower()),
        common_toolchains=("xtensa-esp-elf-gcc", "riscv32-esp-elf-gcc"),
        common_sdks=("ESP-IDF", "Arduino-ESP32"),
        common_flashers=("esptool.py",),
        common_debuggers=("openocd",),
        build_systems=("cmake", "idf.py", "platformio"),
        docs=("https://docs.espressif.com/",),
        notes="VID/PID often identifies the USB-UART bridge, not the ESP SoC itself.",
    ),
    PlatformProfile(
        id="stm32_stlink",
        manufacturer="STMicroelectronics",
        board_family="STM32 Nucleo / Disco (ST-LINK)",
        mcu_family="STM32 (family unknown without further evidence)",
        category="development_board",
        usb_ids=(("0483", "374b"), ("0483", "3748"), ("0483", "3752"), ("0483", "374e")),
        product_substrings=("stm32", "st-link", "stlink", "nucleo"),
        manufacturer_substrings=("stmicroelectronics", "st-link"),
        common_toolchains=("arm-none-eabi-gcc",),
        common_sdks=("STM32Cube", "Zephyr"),
        common_flashers=("openocd", "STM32_Programmer_CLI", "probe-rs"),
        common_debuggers=("openocd", "probe-rs", "pyocd"),
        build_systems=("cmake", "west", "platformio"),
        docs=("https://www.st.com/",),
    ),
    PlatformProfile(
        id="nxp_lpc_link_dap",
        manufacturer="NXP",
        board_family="LPC / i.MX RT with LPC-Link / CMSIS-DAP",
        mcu_family="LPC / i.MX RT (unconfirmed)",
        category="development_board",
        usb_ids=(("1fc9", "0090"), ("1fc9", "0143"), ("0d28", "0204")),
        product_substrings=("lpc-link", "cmsis-dap", "daplink", "imxrt"),
        manufacturer_substrings=("nxp", "arm", "mbed"),
        common_toolchains=("arm-none-eabi-gcc",),
        common_sdks=("MCUXpresso SDK", "Zephyr"),
        common_flashers=("pyocd", "openocd", "probe-rs"),
        common_debuggers=("pyocd", "openocd", "probe-rs"),
        build_systems=("cmake", "west"),
        docs=("https://www.nxp.com/",),
    ),
    PlatformProfile(
        id="raspberry_pi_pico",
        manufacturer="Raspberry Pi",
        board_family="RP2040 / Pico family",
        mcu_family="RP2040 / RP2350 (probable if Picoprobe/Boot strings)",
        category="development_board",
        usb_ids=(("2e8a", "0005"), ("2e8a", "000a"), ("2e8a", "0003")),
        product_substrings=("pico", "rp2040", "picoprobe", "cmsis-dap"),
        manufacturer_substrings=("raspberry pi",),
        common_toolchains=("arm-none-eabi-gcc",),
        common_sdks=("Pico SDK",),
        common_flashers=("picotool", "openocd", "probe-rs"),
        common_debuggers=("openocd", "probe-rs"),
        build_systems=("cmake",),
        docs=("https://www.raspberrypi.com/documentation/microcontrollers/",),
    ),
    PlatformProfile(
        id="cmsis_dap_probe",
        manufacturer="Various",
        board_family="CMSIS-DAP / DAPLink debug probe",
        mcu_family="n/a (probe)",
        category="debug_probe",
        usb_ids=(("0d28", "0204"), ("c251", "f001")),
        product_substrings=("cmsis-dap", "daplink"),
        manufacturer_substrings=("arm", "mbed"),
        common_toolchains=(),
        common_flashers=("pyocd", "openocd", "probe-rs"),
        common_debuggers=("pyocd", "openocd", "probe-rs"),
        build_systems=(),
        notes="Probe identity ≠ target MCU identity.",
    ),
    PlatformProfile(
        id="jlink_probe",
        manufacturer="SEGGER",
        board_family="J-Link",
        mcu_family="n/a (probe)",
        category="debug_probe",
        usb_ids=(("1366", "0101"), ("1366", "0105"), ("1366", "1024")),
        product_substrings=("j-link", "jlink"),
        manufacturer_substrings=("segger",),
        common_flashers=("JLinkExe",),
        common_debuggers=("JLinkGDBServer", "JLinkExe"),
    ),
    PlatformProfile(
        id="ftdi_uart",
        manufacturer="FTDI / common USB-UART",
        board_family="USB serial adapter",
        mcu_family="n/a (adapter — MCU unknown)",
        category="usb_serial_adapter",
        usb_ids=(("0403", "6001"), ("0403", "6010"), ("0403", "6014")),
        product_substrings=("ft232", "ft2232", "usb serial"),
        manufacturer_substrings=("ftdi", "ft"),
        notes="Adapter only; does not identify a connected MCU.",
    ),
)


def match_profiles(
    *,
    vid: Optional[str],
    pid: Optional[str],
    manufacturer: Optional[str],
    product: Optional[str],
) -> list[dict[str, Any]]:
    """Return ranked profile matches with reasons (does not claim confirmation)."""
    vid_l = (vid or "").lower().strip()
    pid_l = (pid or "").lower().strip()
    man = (manufacturer or "").lower()
    prod = (product or "").lower()
    hits: list[dict[str, Any]] = []

    for p in PLATFORM_PROFILES:
        reasons: list[str] = []
        score = 0
        if vid_l and pid_l and (vid_l, pid_l) in p.usb_ids:
            reasons.append(f"usb_id:{vid_l}:{pid_l}")
            score += 50
        elif vid_l and any(v == vid_l for v, _ in p.usb_ids):
            reasons.append(f"usb_vid:{vid_l}")
            score += 15
        for s in p.product_substrings:
            if s and s in prod:
                reasons.append(f"product_substr:{s}")
                score += 10
        for s in p.manufacturer_substrings:
            if s and s in man:
                reasons.append(f"manufacturer_substr:{s}")
                score += 8
        if score <= 0:
            continue
        confidence = "possible"
        if score >= 50:
            confidence = "probable"
        if score >= 70:
            confidence = "confirmed"  # still evidence-limited; see identify.py caps
        hits.append({
            "profile_id": p.id,
            "manufacturer": p.manufacturer,
            "board_family": p.board_family,
            "mcu_family": p.mcu_family,
            "category": p.category,
            "score": score,
            "confidence_hint": confidence,
            "reasons": reasons,
            "common_toolchains": list(p.common_toolchains),
            "common_sdks": list(p.common_sdks),
            "common_flashers": list(p.common_flashers),
            "common_debuggers": list(p.common_debuggers),
            "build_systems": list(p.build_systems),
            "docs": list(p.docs),
            "notes": p.notes,
        })

    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits
