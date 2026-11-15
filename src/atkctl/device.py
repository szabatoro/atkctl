"""Device communication — abstract seam, HID implementation, and test fake.

Architecture
------------
* **AtkDeviceProtocol** (``typing.Protocol``) — the seam that CLI, GUI, and
  tests depend on. Every public method that consumers call lives here.
* **HidDevice** — the real implementation talking to the mouse over USB HID.
* **FakeDevice** — in-memory fake for tests.

Layout
------
The protocol wraps two device slots: wired (0x00, direct USB) and wireless
(0x01, mouse behind receiver). The slot is auto-detected on the first
successful query and remembered.
"""

from __future__ import annotations

import time
from typing import Any, Optional, Protocol, runtime_checkable

import hid

from atkctl.commands import (
    CMD_BATTERY,
    CMD_CONFIG,
    CMD_DEVICE_INFO,
    CMD_DEVICE_VERSION,
    CMD_DONGLE_LED,
    CMD_GET_ONLINE,
    CMD_READ_EEPROM,
    CMD_SET_ANGLE,
    CMD_SET_DEBOUNCE,
    CMD_SET_DONGLE_LIGHT,
    CMD_SET_LOD,
    CMD_SET_MOTION_SYNC,
    CMD_SET_POLLING,
    CMD_SET_RIPPLE,
    CMD_SET_SLEEP,
    CMD_WIRELESS_MODE,
    CMD_WRITE_DPI,
    PACKET_SIZE,
    POLLING_CODES,
    SLOT_WIRED,
    SLOT_WIRELESS,
)
from atkctl.framing import build_request, parse_response
from atkctl.models import BatteryStatus, MouseInfo, lift_off_description


# ── Abstract seam ──────────────────────────────────────────────────────


@runtime_checkable
class AtkDeviceProtocol(Protocol):
    """Abstract interface for the ATK mouse configuration device.

    Implementations: :class:`HidDevice` (real HID) and :class:`FakeDevice` (tests).
    """

    path: str | None
    slot: int | None

    # ── Lifecycle ────────────────────────────────────────────────────
    def open(self) -> AtkDeviceProtocol: ...
    def close(self) -> None: ...
    def __enter__(self) -> AtkDeviceProtocol: ...
    def __exit__(self, *args: Any) -> None: ...

    # ── Queries ──────────────────────────────────────────────────────
    def query_battery(self) -> Optional[BatteryStatus]: ...
    def query_version(self) -> Optional[str]: ...
    def query_config(self) -> Optional[dict]: ...
    def query_dpi_block(self) -> Optional[dict]: ...
    def query_polling_rate(self) -> Optional[int]: ...
    def query_dpi(
        self,
    ) -> tuple[Optional[int], Optional[list[tuple[int, int]]], Optional[int]]: ...
    def query_lift_off(self) -> Optional[str]: ...
    def query_online(self) -> Optional[bool]: ...
    def query_connection_type(self) -> Optional[str]: ...
    def query_wireless_mode(self) -> Optional[str]: ...
    def query_dongle_led(self) -> Optional[str]: ...
    def query_device_info(self) -> Optional[dict[str, Any]]: ...

    # ── EEPROM ───────────────────────────────────────────────────────
    def read_eeprom(self, addr: int, length: int = 2) -> Optional[bytes]: ...

    # ── Bulk read ────────────────────────────────────────────────────
    def read_all(self) -> MouseInfo: ...

    # ── Writes ───────────────────────────────────────────────────────
    def set_polling_rate(self, code: int) -> bool: ...
    def set_dpi(
        self,
        stage: int,
        x_dpi: Optional[int] = None,
        y_dpi: Optional[int] = None,
        red: int = 255,
        green: int = 0,
        blue: int = 0,
        enable: bool = True,
    ) -> bool: ...
    def set_debounce(self, ms: int) -> bool: ...
    def set_motion_sync(self, enabled: bool) -> bool: ...
    def set_angle_snap(self, enabled: bool) -> bool: ...
    def set_ripple_control(self, enabled: bool) -> bool: ...
    def set_sleep_timeout(self, seconds: int) -> bool: ...
    def set_lift_off(self, level: int) -> bool: ...
    def set_dongle_light(self, mode: int) -> bool: ...

    # ── Raw access (debug command) ───────────────────────────────────
    def raw_read(self, size: int = PACKET_SIZE, timeout: float = 0.01) -> list[int]: ...


# ── HID implementation ────────────────────────────────────────────────


class HidDevice:
    """Real HID implementation of :class:`AtkDeviceProtocol`.

    Opens a ``hid.Device`` at the given path and sends/receives
    64-byte BITMOUSE frames.
    """

    def __init__(self, path: str):
        self.path = path
        self._dev: Optional[hid.Device] = None
        self.slot: Optional[int] = None  # auto-detected after first query

    def open(self) -> HidDevice:
        self._dev = hid.Device(
            path=self.path.encode() if isinstance(self.path, str) else self.path
        )
        return self

    def close(self) -> None:
        if self._dev:
            try:
                self._dev.close()
            except Exception:
                pass
            self._dev = None

    def __enter__(self) -> HidDevice:
        return self.open()

    def __exit__(self, *args: Any) -> None:
        self.close()

    # ── Internal: send a command and parse the response ──────────────

    def send(
        self,
        cmd: int,
        data: bytes = b"\x00",
        slot: Optional[int] = None,
        header_byte: int = 0x02,
    ) -> Optional[dict]:
        """Send a command and return the response dict, or None."""
        if slot is None:
            slot = self.slot if self.slot is not None else SLOT_WIRELESS

        dev = self._dev
        assert dev is not None

        dev.nonblocking = False
        pkt = build_request(cmd, data, slot=slot, header_byte=header_byte)
        dev.write(pkt)
        time.sleep(0.15)
        dev.nonblocking = True

        for _ in range(10):
            resp = dev.read(PACKET_SIZE)
            if resp:
                parsed = parse_response(bytes(resp))
                if parsed and parsed["cmd"] == cmd:
                    if self.slot is None:
                        self.slot = slot
                    return parsed
            time.sleep(0.08)
        return None

    # ── EEPROM ───────────────────────────────────────────────────────

    def read_eeprom(self, addr: int, length: int = 2) -> Optional[bytes]:
        """Read ``length`` bytes from EEPROM at ``addr``."""
        data = bytes([addr & 0xFF, (addr >> 8) & 0xFF, length]).ljust(13, b"\x00")
        resp = self.send(CMD_READ_EEPROM, data, header_byte=0x0A)
        if resp:
            p = resp["payload"]
            if len(p) >= 3 + length:
                return bytes(p[3 : 3 + length])
        return None

    # ── High-level queries ───────────────────────────────────────────

    def query_battery(self) -> Optional[BatteryStatus]:
        """Query battery — tries both slots."""
        for slot in [SLOT_WIRELESS, SLOT_WIRED]:
            resp = self.send(CMD_BATTERY, slot=slot)
            if resp:
                p = resp["payload"]
                level = p[0] if len(p) >= 1 else 0
                if level > 0:
                    charging = len(p) > 1 and p[1] != 0
                    voltage = ((p[2] << 8) | p[3]) if len(p) >= 4 else None
                    return BatteryStatus(
                        level=level,
                        charging=charging,
                        voltage_mv=voltage,
                        raw_data=resp["raw"],
                    )
        return None

    def query_version(self) -> Optional[str]:
        """Firmware version as string."""
        resp = self.send(CMD_DEVICE_VERSION, b"\x12\x00\x00\x00\x00", header_byte=5)
        if resp:
            p = resp["payload"]
            if len(p) >= 3:
                return f"{p[0]}.{p[1]}.{p[2]}"
        return None

    def query_config(self) -> Optional[dict]:
        """Read the current mouse config block (command 0x09).

        Returns a dict with keys: profile, polling_rate_hz, polling_code,
        lift_off_level, motion_sync, angle_snap, ripple_control,
        sleep_seconds, debounce_ms.
        """
        resp = self.send(CMD_CONFIG, bytes(17), header_byte=19)
        if resp:
            p = resp["payload"]
            if len(p) >= 12:
                code = p[2]
                return {
                    "profile": p[0],
                    "polling_rate_hz": POLLING_CODES.get(code),
                    "polling_code": code,
                    "lift_off_level": (p[5] + 1) if len(p) > 5 else None,
                    "motion_sync": bool(p[6]) if len(p) > 6 else None,
                    "angle_snap": bool(p[7]) if len(p) > 7 else None,
                    "ripple_control": bool(p[8]) if len(p) > 8 else None,
                    "sleep_seconds": (p[9] | (p[10] << 8)) if len(p) > 10 else None,
                    "debounce_ms": p[11] if len(p) > 11 else None,
                }
        return None

    def query_dpi_block(self) -> Optional[dict]:
        """Read the DPI block via getAddressData from address 1, 7x 10-byte chunks."""
        chunks: list[int] = []
        for i in range(7):
            addr = 1 + i * 10
            data = self.read_eeprom(addr, 10)
            if not data or len(data) < 10:
                return None
            chunks.extend(data)

        if len(chunks) < 66:
            return None

        active_idx = chunks[0]
        stage_count = chunks[1]
        stages: list[tuple[int, int]] = []
        for s in range(8):
            offset = 2 + s * 8
            if offset + 8 > len(chunks):
                break
            x = chunks[offset] | (chunks[offset + 1] << 8)
            y = chunks[offset + 2] | (chunks[offset + 3] << 8)
            if x > 0 or y > 0:
                stages.append((x, y))

        return {
            "active_index": active_idx,
            "stage_count": stage_count,
            "stages": stages,
        }

    def query_polling_rate(self) -> Optional[int]:
        cfg = self.query_config()
        return cfg["polling_rate_hz"] if cfg else None

    def query_dpi(
        self,
    ) -> tuple[Optional[int], Optional[list[tuple[int, int]]], Optional[int]]:
        block = self.query_dpi_block()
        if block and block["stages"]:
            active = block["active_index"]
            stages: list[tuple[int, int]] = block["stages"]
            active_dpi = stages[active][0] if active < len(stages) else stages[0][0]
            return active_dpi, stages, active
        return None, None, None

    def query_lift_off(self) -> Optional[str]:
        cfg = self.query_config()
        if cfg and cfg["lift_off_level"] is not None:
            return lift_off_description(cfg["lift_off_level"])
        return None

    def query_online(self) -> Optional[bool]:
        resp = self.send(CMD_GET_ONLINE, b"\x01\x00")
        if resp:
            p = resp["payload"]
            return len(p) >= 1 and p[0] == 1
        return None

    def query_connection_type(self) -> Optional[str]:
        for slot in [SLOT_WIRELESS, SLOT_WIRED]:
            resp = self.send(CMD_BATTERY, slot=slot)
            if resp:
                p = resp["payload"]
                level = p[0] if len(p) >= 1 else 0
                if level > 0:
                    self.slot = slot
                    return (
                        "Wireless (2.4GHz)"
                        if slot == SLOT_WIRELESS
                        else "Wired USB"
                    )
        return None

    def query_wireless_mode(self) -> Optional[str]:
        resp = self.send(CMD_WIRELESS_MODE, b"\x03\x00")
        if resp:
            p = resp["payload"]
            val = p[0] if len(p) >= 1 else None
            return {0: "Sleeping", 1: "Connected", 2: "Pairing"}.get(
                val, f"Mode {val}"
            )
        return None

    def query_dongle_led(self) -> Optional[str]:
        resp = self.send(CMD_DONGLE_LED, b"\x01\x00")
        if resp:
            p = resp["payload"]
            val = p[0] if len(p) >= 1 else None
            return {0: "Off", 1: "Polling rate", 2: "Battery level", 3: "Low battery"}.get(
                val
            )
        return None

    def query_device_info(self) -> Optional[dict[str, Any]]:
        resp = self.send(CMD_DEVICE_INFO, b"\x06" + bytes(5))
        if resp:
            p = resp["payload"]
            return {
                "raw": p.hex(),
                "unknown_bytes": [x for x in p],
            }
        return None

    # ── Write commands ───────────────────────────────────────────────

    def set_polling_rate(self, code: int) -> bool:
        resp = self.send(CMD_SET_POLLING, bytes([code & 0xFF]), header_byte=0x03)
        return resp is not None

    def set_dpi(
        self,
        stage: int,
        x_dpi: Optional[int] = None,
        y_dpi: Optional[int] = None,
        red: int = 255,
        green: int = 0,
        blue: int = 0,
        enable: bool = True,
    ) -> bool:
        if x_dpi is None or y_dpi is None:
            block = self.query_dpi_block()
            if not block or not block["stages"]:
                return False
            stages: list[tuple[int, int]] = block["stages"]
            if stage >= len(stages) or stages[stage] == (0, 0):
                return False
            x_dpi = stages[stage][0]
            y_dpi = stages[stage][1]

        payload = bytearray(10)
        payload[0] = stage & 0xFF
        payload[1] = x_dpi & 0xFF
        payload[2] = (x_dpi >> 8) & 0xFF
        payload[3] = y_dpi & 0xFF
        payload[4] = (y_dpi >> 8) & 0xFF
        payload[5] = blue & 0xFF
        payload[6] = green & 0xFF
        payload[7] = red & 0xFF
        payload[8] = 0x00
        payload[9] = 1 if enable else 0
        resp = self.send(CMD_WRITE_DPI, bytes(payload), header_byte=0x0C)
        return resp is not None

    def set_debounce(self, ms: int) -> bool:
        resp = self.send(CMD_SET_DEBOUNCE, bytes([ms & 0xFF]), header_byte=0x03)
        return resp is not None

    def set_motion_sync(self, enabled: bool) -> bool:
        resp = self.send(
            CMD_SET_MOTION_SYNC, bytes([1 if enabled else 0]), header_byte=0x03
        )
        return resp is not None

    def set_angle_snap(self, enabled: bool) -> bool:
        resp = self.send(
            CMD_SET_ANGLE, bytes([1 if enabled else 0]), header_byte=0x03
        )
        return resp is not None

    def set_ripple_control(self, enabled: bool) -> bool:
        resp = self.send(
            CMD_SET_RIPPLE, bytes([1 if enabled else 0]), header_byte=0x03
        )
        return resp is not None

    def set_sleep_timeout(self, seconds: int) -> bool:
        seconds = max(0, seconds)
        payload = bytes([seconds & 0xFF, (seconds >> 8) & 0xFF])
        resp = self.send(CMD_SET_SLEEP, payload, header_byte=0x05)
        return resp is not None

    def set_lift_off(self, level: int) -> bool:
        level = max(0, min(10, level))
        resp = self.send(CMD_SET_LOD, bytes([0x00, level & 0xFF]), header_byte=0x04)
        return resp is not None

    def set_dongle_light(self, mode: int) -> bool:
        resp = self.send(
            CMD_SET_DONGLE_LIGHT, bytes([mode & 0xFF]), header_byte=0x03
        )
        return resp is not None

    # ── Raw access ───────────────────────────────────────────────────

    def raw_read(self, size: int = PACKET_SIZE, timeout: float = 0.01) -> list[int]:
        """Read raw HID report bytes (non-blocking)."""
        dev = self._dev
        if dev is None:
            return []
        dev.nonblocking = True
        result = dev.read(size)
        return list(result) if result else []

    # ── Bulk read ────────────────────────────────────────────────────

    def read_all(self) -> MouseInfo:
        """Read all available telemetry into a MouseInfo dataclass."""
        info = MouseInfo(path=self.path, slot=self.slot)

        # Basic info
        info.battery = self.query_battery()
        info.version = self.query_version()
        info.firmware = info.version
        info.device_info = self.query_device_info()
        info.connection_type = self.query_connection_type()

        # Wireless-specific
        if info.connection_type == "Wireless (2.4GHz)":
            try:
                info.wireless_mode = self.query_wireless_mode()
            except Exception:
                pass

        # Config block — single query, reused for all sub-fields
        try:
            cfg = self.query_config()
            if cfg:
                info.polling_rate_hz = cfg.get("polling_rate_hz")
                info.debounce_ms = cfg.get("debounce_ms")
                info.motion_sync = cfg.get("motion_sync")
                info.angle_snap = cfg.get("angle_snap")
                info.ripple_control = cfg.get("ripple_control")
                info.sleep_timeout_s = cfg.get("sleep_seconds")
                lo_level = cfg.get("lift_off_level")
                if lo_level is not None:
                    info.lift_off = lift_off_description(lo_level)
                    info.lift_off_level = lo_level  # ← now in the dataclass
        except Exception:
            pass

        # DPI block
        try:
            info.dpi, info.dpi_stages, info.active_dpi_stage = self.query_dpi()
            info.dpi_stage_count = (
                len(info.dpi_stages) if info.dpi_stages else None
            )
        except Exception:
            pass

        return info


# ── Convenience wrapper (backwards compatible) ─────────────────────────


def create_device(path: str) -> HidDevice:
    """Open a HidDevice at the given path.

    Equivalent to ``HidDevice(path).open()`` but available at module
    level for simple one-shot use.
    """
    return HidDevice(path).open()


# ── In-memory fake for tests ─────────────────────────────────────────


class FakeDevice:
    """In-memory fake implementation of :class:`AtkDeviceProtocol`.

    Stores EEPROM data in a ``bytearray``. All set_* calls succeed
    silently. Raw reads return canned data.

    Example::

        dev = FakeDevice()
        dev.open()
        bat = dev.query_battery()
        assert bat.level == 85
    """

    def __init__(self, eeprom_size: int = 256):
        self.path: str = "/dev/fake"
        self.slot: Optional[int] = SLOT_WIRELESS
        self._eeprom = bytearray(eeprom_size)
        self._open = False

    def open(self) -> FakeDevice:
        self._open = True
        return self

    def close(self) -> None:
        self._open = False

    def __enter__(self) -> FakeDevice:
        return self.open()

    def __exit__(self, *args: Any) -> None:
        self.close()

    # ── EEPROM ───────────────────────────────────────────────────────

    def read_eeprom(self, addr: int, length: int = 2) -> Optional[bytes]:
        if addr + length > len(self._eeprom):
            return None
        return bytes(self._eeprom[addr : addr + length])

    def write_eeprom(self, addr: int, data: bytes) -> None:
        """Write bytes into the fake EEPROM (for test setup)."""
        for i, b in enumerate(data):
            idx = addr + i
            if idx < len(self._eeprom):
                self._eeprom[idx] = b

    # ── Queries ──────────────────────────────────────────────────────

    def query_battery(self) -> Optional[BatteryStatus]:
        return BatteryStatus(level=85, charging=False, voltage_mv=3800)

    def query_version(self) -> Optional[str]:
        return "1.0.0"

    def query_config(self) -> Optional[dict]:
        return {
            "profile": 0,
            "polling_rate_hz": 1000,
            "polling_code": 0,
            "lift_off_level": 4,
            "motion_sync": True,
            "angle_snap": False,
            "ripple_control": False,
            "sleep_seconds": 300,
            "debounce_ms": 4,
        }

    def query_dpi_block(self) -> Optional[dict]:
        return {
            "active_index": 0,
            "stage_count": 8,
            "stages": [
                (400, 400),
                (800, 800),
                (1600, 1600),
                (3200, 3200),
                (6400, 6400),
                (12800, 12800),
                (25600, 25600),
            ],
        }

    def query_polling_rate(self) -> Optional[int]:
        return 1000

    def query_dpi(
        self,
    ) -> tuple[Optional[int], Optional[list[tuple[int, int]]], Optional[int]]:
        block = self.query_dpi_block()
        if block and block["stages"]:
            stages = block["stages"]
            return stages[0][0], stages, 0  # stages[0][0] = X DPI of stage 0
        return None, None, None

    def query_lift_off(self) -> Optional[str]:
        return lift_off_description(4)

    def query_online(self) -> Optional[bool]:
        return True

    def query_connection_type(self) -> Optional[str]:
        return "Wireless (2.4GHz)"

    def query_wireless_mode(self) -> Optional[str]:
        return "Connected"

    def query_dongle_led(self) -> Optional[str]:
        return "Battery level"

    def query_device_info(self) -> Optional[dict[str, Any]]:
        return {"raw": "060000", "unknown_bytes": [6, 0, 0]}

    # ── Writes (all succeed silently) ────────────────────────────────

    def set_polling_rate(self, code: int) -> bool:
        return True

    def set_dpi(
        self,
        stage: int,
        x_dpi: Optional[int] = None,
        y_dpi: Optional[int] = None,
        red: int = 255,
        green: int = 0,
        blue: int = 0,
        enable: bool = True,
    ) -> bool:
        return True

    def set_debounce(self, ms: int) -> bool:
        return True

    def set_motion_sync(self, enabled: bool) -> bool:
        return True

    def set_angle_snap(self, enabled: bool) -> bool:
        return True

    def set_ripple_control(self, enabled: bool) -> bool:
        return True

    def set_sleep_timeout(self, seconds: int) -> bool:
        return True

    def set_lift_off(self, level: int) -> bool:
        return True

    def set_dongle_light(self, mode: int) -> bool:
        return True

    # ── Raw access ───────────────────────────────────────────────────

    def raw_read(self, size: int = PACKET_SIZE, timeout: float = 0.01) -> list[int]:
        return []

    # ── Bulk read ────────────────────────────────────────────────────

    def read_all(self) -> MouseInfo:
        info = MouseInfo(path=self.path, slot=self.slot)
        info.battery = self.query_battery()
        info.version = self.query_version()
        info.firmware = info.version
        info.device_info = self.query_device_info()
        info.connection_type = self.query_connection_type()
        info.wireless_mode = self.query_wireless_mode()

        cfg = self.query_config()
        if cfg:
            info.polling_rate_hz = cfg.get("polling_rate_hz")
            info.debounce_ms = cfg.get("debounce_ms")
            info.motion_sync = cfg.get("motion_sync")
            info.angle_snap = cfg.get("angle_snap")
            info.ripple_control = cfg.get("ripple_control")
            info.sleep_timeout_s = cfg.get("sleep_seconds")
            lo_level = cfg.get("lift_off_level")
            if lo_level is not None:
                info.lift_off = lift_off_description(lo_level)
                info.lift_off_level = lo_level

        dpi_block = self.query_dpi_block()
        if dpi_block and dpi_block["stages"]:
            info.dpi = dpi_block["stages"][0][0]
            info.dpi_stages = dpi_block["stages"]
            info.active_dpi_stage = dpi_block["active_index"]
            info.dpi_stage_count = len(dpi_block["stages"])

        return info