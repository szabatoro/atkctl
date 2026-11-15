"""Low-level BITMOUSE frame building and parsing.

Handles the 64-byte HID frame format used by the NK firmware
(BITMOUSE protocol on usage page 0xFF05, report ID 0x08).

BITMOUSE frame format
---------------------
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

Reference: https://github.com/OpenMouse-Project/mouse-protocol/src/bitmouse
"""

from typing import Optional

from atkctl.commands import PACKET_SIZE, REPORT_ID, SLOT_WIRELESS


def _calc_checksum(buf: bytearray) -> int:
    """Checksum = sum(bytes[2:63]) & 0xFF."""
    return sum(buf[2:]) & 0xFF


def build_request(
    cmd: int,
    data: bytes = b"\x00",
    slot: int = SLOT_WIRELESS,
    header_byte: int = 0x02,
) -> bytes:
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
    payload = data[7 : 7 + length] if length <= len(data) - 7 else data[7:]
    return {
        "cmd": cmd,
        "length": length,
        "payload": payload,
        "raw": data,
        "status": data[2:5],
    }