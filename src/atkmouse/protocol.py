"""ATK Mouse protocol — reverse-engineered for NK firmware (BITMOUSE protocol).

Uses the BITMOUSE frame format (see OpenMouse @openmouse/protocol/bitmouse):
  Request (64 bytes, report ID 0x08 at byte 0):
    [0]: Report ID (0x08)
    [1]: Checksum (sum bytes[2:63] & 0xFF)
    [2]: paramLen
    [3]: cmdSn (0)
    [4]: target/slot (0x00=device, 0x01=mouse behind receiver)
    [5]: Command ID
    [6]: cmdLen (expected reply payload length)
    [7+]: Payload

  Response (64 bytes, report ID 0x08 at byte 0):
    [0]: Report ID (0x08)
    [1]: 0x72
    [2]: status
    [3]: cmdSn
    [4]: target
    [5]: Command ID (echoed)
    [6]: Payload length
    [7+]: Payload
"""

import glob
import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Optional, Any

import hid

PACKET_SIZE = 64
REPORT_ID = 0x08

# ── Command IDs (BITMOUSE protocol) ────────────────────────────────────────
CMD_BATTERY           = 0x07    # Get battery level
CMD_CONFIG            = 0x09    # Get current mouse config (polling, debounce, etc)
CMD_GET_ONLINE        = 0x03    # Get wireless online status (shared byte with CMD_SET_LOD)
CMD_SET_DPI           = 0x02    # Write DPI stage
CMD_SET_LOD           = 0x03    # Set lift-off distance / silent height (shared byte with CMD_GET_ONLINE)
CMD_SET_MOTION_SYNC   = 0x0D    # Set motion sync
CMD_SET_DEBOUNCE      = 0x16    # Set debounce / stabilization time
CMD_DONGLE_LED        = 0x1A    # Get dongle LED mode
CMD_READ_EEPROM       = 0x17    # Get address data (read EEPROM at address)
CMD_DEVICE_INFO       = 0x1C    # Get device info (type) — shared byte with CMD_DEVICE_VERSION
CMD_WIRELESS_MODE     = 0x81    # Get dongle connect status
CMD_DONGLE_VERSION    = 0x88    # Get dongle version
CMD_DEVICE_VERSION    = 0x1C    # Get device firmware version — shared byte with CMD_DEVICE_INFO

# Write commands (BITMOUSE)
CMD_SET_PROFILE       = 0x01    # Set active profile
CMD_WRITE_DPI         = 0x02    # Write DPI stage
CMD_SET_LOD           = 0x03    # Set lift-off (silent height)
CMD_SET_RIPPLE        = 0x0C    # Set ripple control
CMD_SET_MOTION_SYNC   = 0x0D    # Set motion sync
CMD_SET_POLLING       = 0x01    # Set polling rate (setReportRate)
CMD_SET_ANGLE         = 0x0B    # Set linear correction (angle snap)
CMD_SET_SLEEP         = 0x15    # Set sensor sleep time
CMD_SET_DEBOUNCE      = 0x16    # Set stabilization time (debounce)
CMD_SET_DONGLE_LIGHT  = 0x1F    # Dongle LED mode
CMD_SET_LONG_RANGE    = 0x1B    # Set far distance

# BITMOUSE polling rate codes: [code, Hz]
#   0=1000, 1=500, 2=250, 3=125, 4=8000, 5=4000, 6=2000
POLLING_CODES: dict[int, int] = {
    0: 1000, 1: 500, 2: 250, 3: 125,
    4: 8000, 5: 4000, 6: 2000,
}
POLLING_CODES_REV = {v: k for k, v in POLLING_CODES.items()}

# Slot selectors
SLOT_WIRED    = 0x00
SLOT_WIRELESS = 0x01

# ── EEPROM addresses (NK firmware - from ATK HUB capture + live scan) ────
# The NK firmware uses a different address layout than libatk-rs/MyATxMouseControl.
# Confirmed via live EEPROM scan of ATK A9 PRO MAX 2.0 NK.
EEPROM = {
    "polling_rate_code": 0x0002,   # 1 byte: code (0x08=125Hz in standard map)
    "active_stage":      0x0001,   # 1 byte: active DPI stage index
    "active_x_dpi":      0x0003,   # 2 bytes LE: active stage X DPI
    "active_y_dpi":      0x0005,   # 2 bytes LE: active stage Y DPI
    "dpi_stage_base":    0x000A,   # 10 bytes per DPI stage (starts with stage index)
    "dpi_stage_step":    0x000A,   # 10 bytes between stages
    "dpi_lighting":      0x004C,   # 3 bytes: lighting config (confirmed: 00 1e 14)
    "some_setting_46":   0x0046,   # 5 bytes: unknown (05 01 00 00 00 in scan)
}

LIFT_OFF_LABELS: dict[int, str] = {
    1: "Low",
    4: "Medium",
    11: "High",
}


def lift_off_description(level: int) -> str:
    """Human-readable lift-off distance from level (1-11)."""
    mm = 0.6 + level * 0.1  # level 1 → 0.7 mm, level 11 → 1.7 mm
    label = LIFT_OFF_LABELS.get(level)
    if label:
        return f"{mm:.1f} mm  ({label})"
    return f"{mm:.1f} mm"


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class BatteryStatus:
    level: int
    charging: bool = False
    voltage_mv: Optional[int] = None
    raw_data: Optional[bytes] = None


@dataclass
class MouseInfo:
    """Full device snapshot."""
    battery: Optional[BatteryStatus] = None
    version: Optional[str] = None
    polling_rate_hz: Optional[int] = None
    dpi: Optional[int] = None
    dpi_stages: list[tuple[int, int]] = field(default_factory=list)
    active_dpi_stage: Optional[int] = None
    dpi_stage_count: Optional[int] = None
    connection_type: Optional[str] = None
    wireless_mode: Optional[str] = None
    dongle_led_mode: Optional[str] = None
    lift_off: Optional[str] = None
    debounce_ms: Optional[int] = None
    motion_sync: Optional[bool] = None
    angle_snap: Optional[bool] = None
    sleep_timeout_s: Optional[int] = None
    ripple_control: Optional[bool] = None
    device_info: Optional[dict[str, Any]] = None
    slot: Optional[int] = None
    pid: Optional[int] = None
    path: Optional[str] = None
    firmware: Optional[str] = None


# ── Low-level helpers ────────────────────────────────────────────────────

def _calc_checksum(buf: bytearray) -> int:
    """Checksum = sum(bytes[2:63]) & 0xFF."""
    return sum(buf[2:]) & 0xFF


def build_request(cmd: int, data: bytes = b"\x00", slot: int = SLOT_WIRELESS, header_byte: int = 0x02) -> bytes:
    """Build a 64-byte ATK HID request packet.

    Args:
        cmd: Command ID (e.g. 0x07 for battery).
        data: Payload bytes.
        slot: Wired (0x00) or wireless (0x01).
        header_byte: Byte[3] — varies per command. EEPROM uses 0x0a.
    """
    buf = bytearray(PACKET_SIZE)
    buf[0] = REPORT_ID
    buf[2] = 0x72
    buf[3] = header_byte
    buf[5] = slot & 0xFF
    buf[6] = cmd & 0xFF
    buf[7] = len(data) & 0xFF
    if data:
        for i, b in enumerate(data):
            if 8 + i < PACKET_SIZE:
                buf[8 + i] = b
    buf[1] = _calc_checksum(buf)
    return bytes(buf)


def parse_response(data: bytes) -> Optional[dict]:
    """Parse an ATK HID response. Returns dict or None."""
    if len(data) < 8 or data[0] != REPORT_ID or data[1] != 0x72:
        return None
    cmd = data[5]
    length = data[6]
    payload = data[7:7 + length] if length <= len(data) - 7 else data[7:]
    return {"cmd": cmd, "length": length, "payload": payload, "raw": data, "status": data[2:5]}


# ── Device communication ─────────────────────────────────────────────────

class AtkDevice:
    """Opens and talks to the ATK mouse config interface."""

    def __init__(self, path: str):
        self.path = path
        self._dev: Optional[hid.Device] = None
        self.slot: Optional[int] = None  # auto-detected after first query

    def open(self):
        self._dev = hid.Device(path=self.path.encode() if isinstance(self.path, str) else self.path)
        return self

    def close(self):
        if self._dev:
            try:
                self._dev.close()
            except Exception:
                pass
            self._dev = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *args):
        self.close()

    def send(self, cmd: int, data: bytes = b"\x00", slot: Optional[int] = None, header_byte: int = 0x02) -> Optional[dict]:
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
                    # Remember the slot that worked
                    if self.slot is None:
                        self.slot = slot
                    return parsed
            time.sleep(0.08)
        return None

    def read_eeprom(self, addr: int, length: int = 2) -> Optional[bytes]:
        """Read `length` bytes from EEPROM at `addr`.

        Request format (matched to ATK HUB captures):
          byte[3]  = 0x0a                   (EEPROM-specific header)
          payload  = [addr_lo, addr_hi, len] (little-endian addr)
          padded to 13 bytes total

        Response payload (13 bytes):
          bytes 0..2: echoed request (addr_lo, addr_hi, read_len)
          bytes 3+:   actual EEPROM data

        Note: EEPROM stores persistent/power-on defaults. Active settings
        (configured via write commands) may live in RAM and differ.
        """
        data = bytes([addr & 0xFF, (addr >> 8) & 0xFF, length]).ljust(13, b'\x00')
        resp = self.send(CMD_READ_EEPROM, data, header_byte=0x0a)
        if resp:
            p = resp["payload"]
            if len(p) >= 3 + length:
                return bytes(p[3:3 + length])
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
        # Use getDeviceVersion (cmd 0x1C) with BITMOUSE format
        # paramLen=5, cmdLen=3, payload [0x12, 0, 0, 0, 0]
        resp = self.send(CMD_DEVICE_VERSION, b"\x12\x00\x00\x00\x00", header_byte=5)
        if resp:
            p = resp["payload"]
            if len(p) >= 3:
                return f"{p[0]}.{p[1]}.{p[2]}"
        return None

    def query_config(self) -> Optional[dict]:
        """Read the current mouse config block (command 0x09).

        BITMOUSE config response payload:
          [0]:  profile
          [1]:  configVersion
          [2]:  polling rate code (use BITMOUSE_POLLING_CODES)
          [3]:  unknown
          [4]:  silentHeight
          [5]:  offsetCalibration (lift-off level - 1)
          [6]:  motionSync (0/1)
          [7]:  linearCorrection / angle snap (0/1)
          [8]:  rippleControl (0/1)
          [9-10]: sleep timeout seconds (LE uint16)
          [11]: debounce ms
        """
        # BITMOUSE: getCurrentMouseConfig: paramLen=19, cmdLen=17, zero payload
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
        """Read the DPI block via getAddressData from address 1.

        BITMOUSE DPI block (read in 10-byte chunks from address 1, 7 chunks):
          byte[0]:      currentIndex (active stage)
          byte[1]:      stageCount (always 8)
          bytes[2+]:    stages as 8-byte records
            [X_lo, X_hi, Y_lo, Y_hi, blue, green, red, reserved]
            DPI X = X_lo | (X_hi << 8)
            DPI Y = Y_lo | (Y_hi << 8)
        """
        # Read 10-byte chunks from address 1, 7 chunks = 70 bytes
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
        stage_count = chunks[1]  # always 8
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
        """Read polling rate in Hz from the config block."""
        cfg = self.query_config()
        if cfg:
            return cfg["polling_rate_hz"]
        return None

    def query_dpi(self) -> tuple[Optional[int], Optional[list[tuple[int, int]]], Optional[int]]:
        """Returns (active_dpi, list_of_(x_dpi, y_dpi)_pairs, active_index)."""
        block = self.query_dpi_block()
        if block and block["stages"]:
            active = block["active_index"]
            stages: list[tuple[int, int]] = block["stages"]
            active_dpi = stages[active][0] if active < len(stages) else stages[0][0]
            return active_dpi, stages, active
        return None, None, None

    def query_lift_off(self) -> Optional[str]:
        """Read lift-off distance from config block."""
        cfg = self.query_config()
        if cfg and cfg["lift_off_level"] is not None:
            level = cfg["lift_off_level"]
            return lift_off_description(level)
        return None

    def query_online(self) -> Optional[bool]:
        """Is the mouse online (wireless link active)?"""
        resp = self.send(CMD_GET_ONLINE, b"\x01\x00")
        if resp:
            p = resp["payload"]
            return len(p) >= 1 and p[0] == 1
        return None

    def query_connection_type(self) -> Optional[str]:
        """Detect connection type from which slot responds with battery."""
        for slot in [SLOT_WIRELESS, SLOT_WIRED]:
            resp = self.send(CMD_BATTERY, slot=slot)
            if resp:
                p = resp["payload"]
                level = p[0] if len(p) >= 1 else 0
                if level > 0:
                    self.slot = slot
                    return "Wireless (2.4GHz)" if slot == SLOT_WIRELESS else "Wired USB"
        return None

    def query_wireless_mode(self) -> Optional[str]:
        """Wireless mode details."""
        resp = self.send(CMD_WIRELESS_MODE, b"\x03\x00")
        if resp:
            p = resp["payload"]
            val = p[0] if len(p) >= 1 else None
            return {0: "Sleeping", 1: "Connected", 2: "Pairing"}.get(val, f"Mode {val}")
        return None

    def query_dongle_led(self) -> Optional[str]:
        resp = self.send(CMD_DONGLE_LED, b"\x01\x00")
        if resp:
            p = resp["payload"]
            val = p[0] if len(p) >= 1 else None
            return {0: "Off", 1: "Polling rate", 2: "Battery level", 3: "Low battery"}.get(val)
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

    # ── Write commands ──────────────────────────────────────────────

    def set_polling_rate(self, code: int) -> bool:
        """Set polling rate using BITMOUSE code.

        Args:
            code: BITMOUSE polling rate code (0-6).
                  0=1000Hz, 1=500Hz, 2=250Hz, 3=125Hz,
                  4=8000Hz, 5=4000Hz, 6=2000Hz
        """
        resp = self.send(CMD_SET_POLLING, bytes([code & 0xFF]), header_byte=0x03)
        return resp is not None

    def set_dpi(self, stage: int, x_dpi: Optional[int] = None,
                y_dpi: Optional[int] = None,
                red: int = 255, green: int = 0, blue: int = 0,
                enable: bool = True) -> bool:
        """Write a DPI stage, or activate an existing one.

        If x_dpi and y_dpi are omitted, the current values for the
        given stage are read from the device and written back — this
        effectively just switches the active stage.

        Args:
            stage:  Stage index (0-7).
            x_dpi:  X-axis DPI value (omit to read existing and activate).
            y_dpi:  Y-axis DPI value (omit to read existing and activate).
            red:    Red LED value (0-255, default 255).
            green:  Green LED value (0-255, default 0).
            blue:   Blue LED value (0-255, default 0).
            enable: If True, this stage becomes active.
        """
        if x_dpi is None or y_dpi is None:
            # Read current values for this stage
            block = self.query_dpi_block()
            if not block or not block["stages"]:
                return False
            stages: list[tuple[int, int]] = block["stages"]
            if stage >= len(stages) or stages[stage] == (0, 0):
                return False  # stage not configured, can't activate without values
            x_dpi = stages[stage][0]
            y_dpi = stages[stage][1]

        payload = bytearray(10)
        payload[0] = stage & 0xFF
        payload[1] = x_dpi & 0xFF          # X DPI lo
        payload[2] = (x_dpi >> 8) & 0xFF   # X DPI hi
        payload[3] = y_dpi & 0xFF          # Y DPI lo
        payload[4] = (y_dpi >> 8) & 0xFF   # Y DPI hi
        payload[5] = blue & 0xFF
        payload[6] = green & 0xFF
        payload[7] = red & 0xFF
        payload[8] = 0x00                   # reserved
        payload[9] = 1 if enable else 0
        resp = self.send(CMD_WRITE_DPI, bytes(payload), header_byte=0x0c)
        return resp is not None

    def set_debounce(self, ms: int) -> bool:
        """Set debounce/stabilization time in milliseconds."""
        resp = self.send(CMD_SET_DEBOUNCE, bytes([ms & 0xFF]), header_byte=0x03)
        return resp is not None

    def set_motion_sync(self, enabled: bool) -> bool:
        """Enable or disable motion sync."""
        resp = self.send(CMD_SET_MOTION_SYNC, bytes([1 if enabled else 0]), header_byte=0x03)
        return resp is not None

    def set_angle_snap(self, enabled: bool) -> bool:
        """Enable or disable angle snapping (linear correction)."""
        resp = self.send(CMD_SET_ANGLE, bytes([1 if enabled else 0]), header_byte=0x03)
        return resp is not None

    def set_ripple_control(self, enabled: bool) -> bool:
        """Enable or disable ripple control."""
        resp = self.send(CMD_SET_RIPPLE, bytes([1 if enabled else 0]), header_byte=0x03)
        return resp is not None

    def set_sleep_timeout(self, seconds: int) -> bool:
        """Set auto-sleep timeout in seconds (0 = never sleep)."""
        seconds = max(0, seconds)
        payload = bytes([seconds & 0xFF, (seconds >> 8) & 0xFF])
        resp = self.send(CMD_SET_SLEEP, payload, header_byte=0x05)
        return resp is not None

    def set_lift_off(self, level: int) -> bool:
        """Set lift-off distance (offset calibration level).

        Args:
            level: Offset calibration level (0-10).
                   Lift-off level = level + 1.
                   level=0 → ~0.7 mm,  level=3 → ~1.0 mm,  level=10 → ~1.7 mm
        """
        level = max(0, min(10, level))
        resp = self.send(CMD_SET_LOD, bytes([0x00, level & 0xFF]), header_byte=0x04)
        return resp is not None

    def set_dongle_light(self, mode: int) -> bool:
        """Set dongle LED mode.

        Args:
            mode: LED mode (0 = Off, 1 = Polling rate,
                  2 = Battery level, 3 = Low battery, 4-5 = other effects)
        """
        resp = self.send(CMD_SET_DONGLE_LIGHT, bytes([mode & 0xFF]), header_byte=0x03)
        return resp is not None

    def read_all(self) -> MouseInfo:
        """Read all available telemetry into a MouseInfo dataclass."""
        info = MouseInfo(path=self.path, slot=self.slot)

        # Basic info
        info.battery = self.query_battery()
        info.version = self.query_version()
        info.firmware = info.version  # same call, reuse
        info.device_info = self.query_device_info()
        info.connection_type = self.query_connection_type()

        # Wireless-specific
        if info.connection_type == "Wireless (2.4GHz)":
            info.wireless_mode = self.query_wireless_mode()

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
        except Exception:
            pass

        # DPI block — 7 EEPROM reads, slow but only done once
        try:
            info.dpi, info.dpi_stages, info.active_dpi_stage = self.query_dpi()
            info.dpi_stage_count = len(info.dpi_stages) if info.dpi_stages else None
        except Exception:
            pass

        return info


# ── Convenience wrappers (backwards-compatible) ──────────────────────────

def query_battery(device_path: str) -> Optional[BatteryStatus]:
    """Legacy wrapper — query battery on any path."""
    with AtkDevice(device_path) as dev:
        return dev.query_battery()


def find_atk_hidraw5() -> Optional[str]:
    """Find the hidraw path for the ATK config interface (usage page 0xFF05)."""
    try:
        for d in hid.enumerate():
            if (d.get("vendor_id") == 0x373b and
                d.get("usage_page") == 0xFF05 and
                d.get("usage") == 0x0001):
                path = d.get("path", b"")
                if path:
                    return path.decode() if isinstance(path, bytes) else path
    except Exception:
        pass
    try:
        for hidraw in sorted(glob.glob("/dev/hidraw*")):
            r = subprocess.run(
                ["udevadm", "info", "-q", "property", hidraw],
                capture_output=True, text=True, timeout=5,
            )
            if "ID_VENDOR_ID=373b" in r.stdout and "ID_USB_INTERFACE_NUM=02" in r.stdout:
                return hidraw
    except Exception:
        pass
    return None


def enumerate_atk_interfaces() -> list[dict]:
    interfaces = []
    for d in hid.enumerate():
        if d.get("vendor_id") == 0x373b:
            path = d.get("path", b"")
            interfaces.append({
                "path": path.decode() if isinstance(path, bytes) else str(path),
                "usage_page": d["usage_page"],
                "usage": d["usage"],
                "interface_number": d.get("interface_number", -1),
                "product": d.get("product_string", ""),
            })
    return interfaces