"""BITMOUSE command IDs, polling rate codes, slot selectors, and EEPROM map.

Constants reverse-engineered from ATK HUB WebHID traffic and cross-referenced
against OpenMouse's BITMOUSE codec.
"""

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