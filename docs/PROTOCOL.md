# ATK Mouse HID Protocol — Reverse Engineering Report

**Device:** ATK A9 PRO MAX 2.0 NK (also ATK ZERO and newer ATK/VXE/VGN mice)  
**Vendor:** ATK (Compx) — USB VID `0x373b`  
**Wired PID:** `0x1264`  
**8K NANO Dongle PID:** `0x11dc`  
**Firmware:** NK 2.0 (Nordic nRF52840-based)

This mouse uses the **BITMOUSE protocol** (aka "getAddressData" framing), shared by the ATK ZERO family. It is *not* the same as the 16-byte EEPROM protocol used by older ATK/Endgame Gear mice — see [OpenMouse bitmouse codec](https://github.com/OpenMouse-Project/mouse-protocol/tree/main/src/bitmouse) for the canonical reference.

---

## Table of Contents

1. [Device Topology](#1-device-topology)
2. [Config Interface Discovery](#2-config-interface-discovery)
3. [BITMOUSE Frame Format](#3-bitmouse-frame-format)
4. [Battery Query](#4-battery-query)
5. [Read Current Config (getCurrentMouseConfig)](#5-read-current-config-getcurrentmouseconfig)
6. [EEPROM / Address Data Access](#6-eeprom--address-data-access)
7. [DPI Block](#7-dpi-block)
8. [Command Reference](#8-command-reference)
9. [Wired vs Wireless Differences](#9-wired-vs-wireless-differences)
10. [Mouse Sleeping](#10-mouse-sleeping)
11. [Sniffing Methodology](#11-sniffing-methodology)
12. [References](#12-references)

---

## 1. Device Topology

The mouse exposes three USB HID interfaces:

| Interface | Usage Page | Direction | Report ID | Role |
|-----------|-----------|-----------|-----------|------|
| 0 (hidraw3) | `0x0001` (Generic Desktop) | IN only | `0x01` (mouse) / `0x02` (keyboard) | Standard HID mouse + keyboard |
| 1 (hidraw4) | `0xFFB3` (Vendor) | **OUT** 64B / **IN** 12B | None | Alternate vendor interface |
| 2 (hidraw5) | `0xFFB1` (Vendor) | IN 12B | `0x09` | Vendor status notifications |
| 2 (hidraw5) | `0xFF05` (Vendor) | **OUT** 63B / **IN** 63B | `0x08` | **Primary config interface** |

The **primary control channel** is the `0xFF05` collection on hidraw5 with report ID `0x08`. This is where all BITMOUSE command/response traffic flows.

---

## 2. Config Interface Discovery

```python
import hid
for d in hid.enumerate():
    if d.get("vendor_id") == 0x373b:
        print(f'{d["path"]}  page=0x{d["usage_page"]:04X} usage=0x{d["usage"]:04X}')
```

The config interface is identified by `usage_page == 0xFF05` (Nordic nRF vendor page). This is the only interface that accepts both output and input reports of 64 bytes.

On Linux, this maps to `/dev/hidraw5` (the exact number depends on enumeration order).

---

## 3. BITMOUSE Frame Format

All commands and responses use **64-byte HID reports** on report ID `0x08`. The format was confirmed by cross-referencing ATK HUB WebHID captures against the [OpenMouse BITMOUSE codec](https://github.com/OpenMouse-Project/mouse-protocol/blob/main/src/bitmouse/index.ts).

### 3.1 Request (Host → Device)

```
Byte 0:   0x08              — HID Report ID (fixed)
Byte 1:   checksum           — sum(bytes[2:63]) & 0xFF
Byte 2:   paramLen           — length of request payload (varies by command)
Byte 3:   0x00               — cmdSn (sequence number, always 0 in requests)
Byte 4:   target             — 0x00 = device, 0x01 = mouse behind receiver
Byte 5:   command_id         — command opcode
Byte 6:   cmdLen             — expected reply payload length
Byte 7+:  payload data       — command-specific; zero-padded to end
Bytes N..63: 0x00             — zero padding
```

**Checksum** = `sum(bytes[2:63]) & 0xFF`. Since byte[1] (the checksum) is set to 0x00 before computation and written afterwards, the initial zero contributes nothing to the sum.

### 3.2 Response (Device → Host)

```
Byte 0:   0x08              — HID Report ID (fixed)
Byte 1:   0x72               — response marker
Byte 2:   status             — 0x00 = OK, 0xFF = error
Byte 3:   cmdSn              — echoed from request
Byte 4:   target             — echoed from request
Byte 5:   command_id         — echoed command opcode
Byte 6:   payload_length     — number of valid bytes in payload
Byte 7+:  payload data       — command-specific response data
```

The device does not clear the tail of the reply buffer — bytes beyond `payload_length` are leftovers from the previous exchange and must be discarded.

### 3.3 Key difference from older ATK protocol

Older ATK mice (Endgame Gear, libatk-rs) use a different frame format on 0xFF02:
- byte[3] = 0x02 (protocol version), not paramLen
- byte[7] = data_length, not cmdLen
- 0x55 checksum pairs on every value

Our NK firmware mouse uses BITMOUSE exclusively. The two protocols are **not interchangeable** — commands and field meanings differ.

---

## 4. Battery Query

Command `0x07` (getBatteryLevel). BITMOUSE lengths: paramLen=2, cmdLen=1.

### 4.1 Request

```
08 [cs] 72 02 00 [target] 07 01 00 00 00 ... (to 64 bytes)
                  │    │  │  │
                  │    │  │  └── payload byte (0x00 = query)
                  │    │  └───── cmdLen (expected reply length = 1)
                  │    └──────── command 0x07 (getBatteryLevel)
                  └─────────── paramLen (request payload length = 2)
```

**Wired example** (captured from ATK HUB):
```
08 7c 72 02 00 00 07 01 00 00 ...
               ↑ target=0x00 (device)
```

**Wireless example** (via 2.4GHz dongle):
```
08 7d 72 02 00 01 07 01 00 00 ...
               ↑ target=0x01 (mouse behind receiver)
```

### 4.2 Response

```
08 72 00 [cmdSn] [target] 07 01 [level] [charging] [voltage_hi] [voltage_lo] 00 ...
```

| Offset (from byte 7) | Size | Description |
|----------------------|------|-------------|
| 7 | 1 | Battery level (0–100 percent) |
| 8 | 1 | Charging status (0 = discharging, 1 = charging) |
| 9–10 | 2 | Battery voltage in mV (big-endian) |

A response with `byte[7] == 0` means the mouse is offline/asleep.

---

## 5. Read Current Config (getCurrentMouseConfig)

Command `0x09` (getCurrentMouseConfig). BITMOUSE lengths: paramLen=19, cmdLen=17.

This is the **primary way to read active settings**. It returns a 12-byte config block:

### 5.1 Request

```
08 [cs] 72 13 00 [target] 09 11 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 ...
               ↑ paramLen=0x13 (19)
                                    ↑ cmdLen=0x11 (17)
```

Payload is 17 zero bytes.

### 5.2 Response payload format

```
[0]:  profile                   — active profile index
[1]:  configVersion             — configuration version
[2]:  polling rate code         — see §8.1
[3]:  unknown
[4]:  silentHeight
[5]:  offsetCalibration         — lift-off level = this + 1 (code 1 = 0.7 mm)
[6]:  motionSync                — 0/1
[7]:  linearCorrection          — angle snapping, 0/1
[8]:  rippleControl             — 0/1
[9-10]: sleep timeout seconds   — little-endian uint16
[11]: debounce ms
```

### 5.3 Polling Rate Codes (BITMOUSE)

| Code | Frequency |
|------|-----------|
| 0 | 1000 Hz (1K) |
| 1 | 500 Hz |
| 2 | 250 Hz |
| 3 | 125 Hz |
| 4 | 8000 Hz (8K) |
| 5 | 4000 Hz (4K) |
| 6 | 2000 Hz (2K) |

These codes are **completely different** from the 0x55-checksum-pair encoding used by older ATK firmware.

### 5.4 Lift-off Distance

Lift-off level = `offsetCalibration + 1`. The level uses tenths of a millimetre offset by 6:

| Level | Millimetres |
|-------|-------------|
| 1 | 0.7 mm (Low) |
| 4 | 1.0 mm (Medium) |
| 11 | 1.7 mm (High) |

The full range is 1–11 (0.7–1.7 mm).

---

## 6. EEPROM / Address Data Access

Command `0x17` (getAddressData). BITMOUSE lengths: paramLen=10, cmdLen=13.

This reads arbitrary EEPROM addresses on the device. Used for reading the DPI block and other persistent storage.

### 6.1 Request

```
08 [cs] 72 0a 00 [target] 17 0d [addr_lo] [addr_hi] [len] [zeros...]
```

- byte[3] = 0x0a (paramLen = 10 for getAddressData)
- byte[6] = 0x17 (command)
- byte[7] = 0x0d (cmdLen = 13 — expected reply length)
- payload: `[addr_lo, addr_hi, read_len]` — 3 bytes, **little-endian address**, followed by 10 zero bytes (total 13)

Note: There is **no 0x0D marker byte** in the payload. The format is simply `[addr_lo, addr_hi, len]` with no prefix marker. This was confirmed by comparing ATK HUB captures.

### 6.2 Response

```
08 72 00 [cmdSn] [target] 17 0d [addr_lo] [addr_hi] [len] [data...]
                                    ↑ echo ──┘   └ data (read_len bytes)
```

The first 3 payload bytes echo the address and length. Actual data starts at **payload offset 3**.

### 6.3 EEPROM Map (NK Firmware)

The NK firmware's EEPROM layout differs significantly from the libatk-rs/MyATxMouseControl map. The live EEPROM contents were scanned:

| Address | Content |
|---------|---------|
| `0x0000` | Header area (0x00 = unknown, 0x01 = active stage index) |
| `0x0002` | Unknown (0x08 in current scan) |
| `0x0003-0x0006` | Stage data (values vary) |
| `0x000A` | Start of DPI stage array (10-byte steps, PAW3955Master format) |
| `0x004C` | DPI lighting config: `00 1e 14` (confirmed from capture) |
| `0x0046-0x0051` | Additional settings (~12 bytes) |

Note: **Active settings** (polling rate, debounce, motion sync, etc.) are read via `getCurrentMouseConfig` (command 0x09), not from EEPROM. The EEPROM stores persistent/power-on defaults and DPI stage tables.

---

## 7. DPI Block

DPI data is read via `getAddressData` (0x17) starting from **address 1**, in 10-byte chunks, 7 chunks total.

### 7.1 Read Process

```python
for i in range(7):
    addr = 1 + i * 10
    data = read_eeprom(addr, 10)  # uses getAddressData
```

Total: 70 bytes read (7 × 10). Meaningful data is 66 bytes (2 header + 8 × 8-byte stages).

### 7.2 DPI Block Format

```
Byte 0:      currentIndex      — active DPI stage index
Byte 1:      stageCount        — always 8 (table size, not number of enabled stages)
Byte 2+:     stages (8 records × 8 bytes each):

  [X_lo, X_hi, Y_lo, Y_hi, blue, green, red, reserved]
  
  DPI = X_lo | (X_hi << 8)    — direct uint16 LE value
```

Unconfigured stages read 0 DPI. Enabled stages are the leading run of non-zero entries.

### 7.3 PAW3955Master DPI Encoding

This sensor uses raw uint16 LE values (no `+ 1` offset, no nibble packing):
- X DPI = `X_lo | (X_hi << 8)` — e.g. `0xB8 0x0B` = 3000 DPI
- Y DPI = `Y_lo | (Y_hi << 8)` — same encoding

See OpenMouse `atkEncodeDpiAxisPaw3955Master` / `atkDecodeDpiAxisPaw3955Master`:

```typescript
function atkDecodeDpiAxisPaw3955Master(lo: number, hi: number, doubled: boolean): number {
  const dpi = (lo | (hi << 8)) + 1;
  return doubled ? dpi * 2 : dpi;
}
```

The `doubled` flag comes from `flags & 0x01` (byte[4] of the 6-byte PAW3955Master stage record). In the DPI block format, this flag is part of the `reserved` byte (byte[7] of the 8-byte record).

---

## 8. Command Reference

All command IDs are for the **BITMOUSE protocol** (NK firmware). These differ from the older ATK/Endgame Gear command IDs.

### 8.1 Read Commands

| Cmd | Name | paramLen | cmdLen | Purpose |
|-----|------|----------|--------|---------|
| `0x03` | getOnlineStatus | 3 | 1 | Check if mouse is connected wirelessly |
| `0x07` | getBatteryLevel | 2 | 1 | Read battery % |
| `0x09` | getCurrentMouseConfig | 19 | 17 | Read config block (polling, debounce, etc.) |
| `0x17` | getAddressData | 10 | 13 | Read EEPROM at address |
| `0x1A` | getDongleLEDMode | 2 | 1 | Dongle LED mode (0=off, 1=polling, 2=battery, 3=low batt) |
| `0x1C` | getDeviceVersion | 5 | 3 | Read firmware version (3 bytes: major.minor.patch) |
| `0x4A` | getDeviceType | 6 | 6 | Read device capabilities / type |
| `0x81` | getDongleConnectStatus | 3 | 1 | Dongle wireless status (0=sleeping, 1=connected) |
| `0x88` | getDongleVersion | 5 | 3 | Dongle firmware version |

### 8.2 Write Commands

| Cmd | Name | Purpose |
|-----|------|---------|
| `0x01` | setReportRate | Set polling rate (BITMOUSE code) |
| `0x02` | setDpi | Write DPI stage (10-byte payload) |
| `0x03` | setSilentHeight | Set lift-off distance |
| `0x0B` | setLinearCorrection | Set angle snapping (0/1) |
| `0x0C` | setRippleControl | Set ripple control (0/1) |
| `0x0D` | setMotionSync | Set motion sync (0/1) |
| `0x15` | setSensorSleepTime | Set sleep timeout (seconds, LE uint16) |
| `0x16` | setStabilizationTime | Set debounce ms |
| `0x1B` | setFarDistance | Set long-range mode (0/1) |
| `0x1F` | setDongleLight | Dongle LED effect mode |

### 8.3 DPI Write (0x02) Payload

10-byte payload for `setDpi`:

```
[0]:    stage index (0-7)
[1-2]:  X DPI (LE uint16)
[3-4]:  Y DPI (LE uint16)
[5]:    blue
[6]:    green
[7]:    red
[8]:    0x00 (reserved)
[9]:    enable — 1 to apply this stage, 0 to only store
```

Enabling a stage (setting `enable=1`) makes it the active stage.

---

## 9. Wired vs Wireless Differences

### 9.1 Target Byte

| Connection | Target value (byte[4]) |
|-----------|----------------------|
| Wired USB | `0x00` |
| 2.4GHz wireless (dongle) | `0x01` (mouse behind receiver) |

When sending a battery query, **try target `0x01` first** (wireless), then fall back to `0x00` (wired). The dongle responds correctly with target `0x01`; the wired mouse responds to both but prefers `0x00`.

### 9.2 Response Status

In wired mode, the response status (byte[2]) is often `0x00`. With the wireless dongle, status may vary (`0x00`, `0x05`, or other values depending on sub-device).

---

## 10. Mouse Sleeping

When the mouse is wirelessly connected but **asleep** (power saving), the dongle responds to all queries with minimal/default data:
- Battery query returns `byte[7] = 0` (0%)
- EEPROM reads may return stale/cached data

The mouse needs to be moving (awake) for reliable readings. If a query returns zero data, wait 1–2 seconds and retry. The `atkmouse battery` command doubles as a wake-up call.

---

## 11. Sniffing Methodology

### 11.1 Chrome Extension Approach

The protocol was reverse-engineered using a custom Chrome extension that intercepts WebHID API calls:

```javascript
// Hook WebHID sendReport to capture outgoing commands
HIDDevice.prototype.sendReport = async function(reportId, data) {
    console.log(`OUT reportId=0x${reportId.toString(16)}: ${bytesToHex(data)}`);
    return await originalSendReport.call(this, reportId, data);
};

// Hook inputreport events to capture device responses
HIDDevice.prototype.addEventListener = function(type, listener, options) {
    if (type === 'inputreport') {
        const wrapped = (event) => {
            console.log(`IN reportId=0x${event.reportId.toString(16)}: ${bytesToHex(event.data)}`);
            listener(event);
        };
        return originalAddEventListener.call(this, type, wrapped, options);
    }
    return originalAddEventListener.call(this, type, listener, options);
};
```

The protocol was reverse-engineered by intercepting ATK HUB's WebHID API calls with a Chrome extension that hooks `HIDDevice.sendReport` and `inputreport` events while the mouse was connected.

### 11.2 Cross-referencing

The captured packets were compared against the [OpenMouse BITMOUSE codec](https://github.com/OpenMouse-Project/mouse-protocol/blob/main/src/bitmouse/index.ts), which provided the frame format, command IDs, and DPI encoding. The OpenMouse codec was written by reverse-engineering the same ATK HUB WebHID traffic and testing against an ATK ZERO on hardware.

---

## 12. References

### Primary reference (used for this implementation):

- **OpenMouse / mouse-protocol** — BITMOUSE codec and WebHID drivers  
  https://github.com/OpenMouse-Project/mouse-protocol  
  `src/bitmouse/index.ts` — frame format, command IDs, DPI encoding  
  `src/drivers/atk/bitmouse-hid.ts` — ATK BITMOUSE driver

### Tools used in this RE:

- Linux `hidapi` (Python `hid` bindings) for device enumeration and packet replay
- [ATK HUB](https://hub.atk.pro/) v3.2.29 — manufacturer's WebHID config panel
- Chrome extension for WebHID traffic interception
- Wireshark + usbmon (optional, for USB-level verification)

---

## Appendix A: Known PIDs

These ATK/VXE/VGN product IDs are confirmed to use the BITMOUSE protocol at 0xFF05:

| PID | Device |
|-----|--------|
| `0x1264` | ATK A9 PRO MAX 2.0 NK (wired) |
| `0x11dc` | NK mouse 8K NANO dongle |
| `0x1154` | ATK ZERO (wired) |
| `0x1155` | ATK ZERO (receiver) |
| `0x11d9` | ATK A9 Ultimate / F1 Ultimate (8K dongle) |
| `0x1085` | VXE R1 SE/SE+ (1K dongle) |

Most ATK/VXE/VGN mice with firmware NK 2.0+ use this protocol. The key identifier is the **0xFF05 vendor usage page** with **report ID 0x08** using the BITMOUSE framing (paramLen/cmdLen at bytes 2 and 6).

## Appendix B: Example Packet Walkthrough

### Wireless Battery Query

**Request:**
```
Position:  00 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 ...
Hex:       08 7d 72 02 00 01 07 01 00 00 00 00 00 00 00 00 ...
```
- `08` = Report ID
- `7d` = Checksum
- `72` = BITMOUSE command code
- `02` = paramLen (request payload length = 2)
- `00` = cmdSn (sequence)
- `01` = target (0x01 = mouse behind receiver)
- `07` = Command: getBatteryLevel
- `01` = cmdLen (expected reply length = 1)
- `00` = Payload byte

**Response:**
```
Position:  00 01 02 03 04 05 06 07 08 09 10 11 12 13 ...
Hex:       08 72 00 [sn] [tgt] 07 01 5a c2 10 00 00 00 ...
                                         │  │  │
                                         │  │  └── 0x10 = voltage LSB
                                         │  └───── 0xC2 = voltage MSB (0xC210 = 49616 mV)
                                         └──────── 0x5A = 90%
```

### EEPROM Read (getAddressData)

**Request:**
```
08 ac 72 0a 00 01 17 0d 01 00 0a 00 00 00 00 00 00 00 00 00 00 00 ...
```
- `08` = Report ID
- `ac` = Checksum
- `72` = BITMOUSE command code
- `0a` = paramLen (10)
- `00` = cmdSn
- `01` = target (mouse behind receiver)
- `17` = Command: getAddressData
- `0d` = cmdLen (13)
- `01 00 0a` = Payload: addr_lo=0x01, addr_hi=0x00, read_len=0x0a (10)
- `00 00...` = Zero padding to 13 bytes

**Response:**
```
08 72 00 [sn] [tgt] 17 0d 01 00 0a 01 08 e8 03 e8 03 00 00 ff 00
```
- Echo: `01 00 0a` (3 bytes: addr_lo, addr_hi, read_len)
- Data (10 bytes): `01 08 e8 03 e8 03 00 00 ff 00`
  - `e8 03` = 1000 DPI (LE uint16)
  - Second `e8 03` = 1000 DPI (Y axis)