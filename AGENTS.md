# atkctl — Agent Guidance

> 🧠 **Vibecoded with [OpenCode](https://opencode.ai/)** — this project was built entirely through iterative AI pair-programming. The protocol reverse-engineering, CLI, GUI, Arch packaging, and documentation are all the result of agent-driven development. Treat the whole codebase as AI-native — agents are expected to edit, refactor, and extend it freely.

## Project Overview

Python CLI + GUI tool for reading and configuring ATK A9 PRO MAX 2.0 NK gaming mice (and compatible ATK/VXE/VGN models). Communicates over USB HID using the **BITMOUSE protocol** (report ID `0x08`, usage page `0xFF05`).

The protocol was reverse-engineered by intercepting WebHID traffic from [ATK HUB](https://hub.atk.pro/) and cross-referenced against [OpenMouse mouse-protocol](https://github.com/OpenMouse-Project/mouse-protocol).

## Key Files

| File | What it does |
|------|-------------|
| `src/atkctl/commands.py` | BITMOUSE command IDs, polling rate codes, slot constants, EEPROM map |
| `src/atkctl/models.py` | Data models — `BatteryStatus`, `MouseInfo`, `PanelData` TypedDict, helpers |
| `src/atkctl/framing.py` | BITMOUSE frame building (`build_request`) and parsing (`parse_response`) |
| `src/atkctl/discovery.py` | Device discovery — `find_atk_hidraw5()`, `enumerate_atk_interfaces()` |
| `src/atkctl/device.py` | Abstract seam (`AtkDeviceProtocol`), HID impl (`HidDevice`), test fake (`FakeDevice`) |
| `src/atkctl/cli.py` | CLI commands — `battery`, `status`, `monitor`, `discover`, `debug`, `eeprom`, all `set-*` commands |
| `src/atkctl_gui/` | Qt6 GUI frontend (PySide6) — independent `pyproject.toml` at `src/atkctl_gui/pyproject.toml` |
| `CONTEXT.md` | Domain glossary and architecture decisions |
| `tests/test_device.py` | 38 tests using the `FakeDevice` seam |
| `docs/PROTOCOL.md` | Full protocol documentation (BITMOUSE frame format, commands, DPI block, config block) |
| `udev/70-atkctl-mouse.rules` | udev rules — grants seat-local users ACL-based access |
| `PKGBUILD` | Arch Linux package definition (CLI) |
| `PKGBUILD-gui` | Arch Linux package definition (GUI) |

## Protocol Summary (BITMOUSE)

This is NOT the same as the older ATK/Endgame Gear protocol (libatk-rs, MyATxMouseControl). Our NK firmware uses **BITMOUSE**.

**Frame format** (64 bytes, report ID 0x08):
```
Request:  [0] 0x08 [1] cs [2] 0x72 [3] paramLen [4] target [5] cmdId [6] cmdLen [7+] payload
Response: [0] 0x08 [1] 0x72 [2] status [3] cmdSn [4] target [5] cmdId [6] payloadLen [7+] payload
```

**Polling rate codes:** `{0: 1000Hz, 1: 500Hz, 2: 250Hz, 3: 125Hz, 4: 8000Hz, 5: 4000Hz, 6: 2000Hz}`

**Config block** (command `0x09`): The primary way to read active settings — polling rate at `payload[2]`, lift-off at `payload[5]`, motion sync at `[6]`, ripple at `[8]`, sleep at `[9-10]`, debounce at `[11]`.

**DPI**: Read via `getAddressData` (0x17) from address 1, in 10-byte chunks (7 chunks). Stage records: `[X_lo, X_hi, Y_lo, Y_hi, blue, green, red, reserved]`. DPI = `X_lo | (X_hi << 8)` — direct LE uint16.

## Running

```bash
uv run atkctl battery        # Quick battery read
uv run atkctl status         # Full telemetry dump
uv run atkctl status --json  # Machine-readable
uv run atkctl monitor        # Continuous polling
uv run atkctl eeprom 0x0001  # Read arbitrary EEPROM address
uv run atkctl eeprom 0x0000 --scan 0x0060  # Scan EEPROM range
```

## Common Pitfalls

1. **Mouse goes to sleep** — After ~60s of inactivity, the mouse enters power-saving mode. All reads return stale/null data. Always call `battery` or a command first to wake it, then wait 1-2s before reading EEPROM.
2. **EEPROM ≠ active settings** — EEPROM stores persistent defaults. Active settings (polling, debounce, etc.) are read from command `0x09` (getCurrentMouseConfig), not EEPROM.
3. **Two different protocol families** — Older ATK mice use a different frame format (16-byte EEPROM commands on 0xFF02, 0x55 checksum pairs). Our NK firmware uses BITMOUSE (64-byte frames on 0xFF05, paramLen/cmdLen framing). Do not mix them.
4. **Target byte** — Wireless dongle mode uses `target=0x01` (mouse behind receiver), wired uses `target=0x00` (direct device). Always try wireless first, fall back to wired.
5. **Response tail** — The device doesn't clear the reply buffer. Bytes beyond the reported payload length are leftovers and must be discarded.

## Next Steps / Things to Build

- **`query_dongle_version`** — The dongle has its own firmware; reading it would let status show both mouse and dongle versions.
- **Profile switching** — Command `0x01` writes profiles; a `set-profile` subcommand could switch between stored configs.
- **Button remapping** — The EEPROM has button assignment data (addresses `0x0060`-`0x0074`). A `buttons` command could read/decode them.

## References

- **OpenMouse BITMOUSE codec**: https://github.com/OpenMouse-Project/mouse-protocol/blob/main/src/bitmouse/index.ts
- **ATK HUB**: https://hub.atk.pro/
- **OpenMouse ATK driver**: https://github.com/OpenMouse-Project/mouse-protocol/blob/main/src/drivers/atk/bitmouse-hid.ts