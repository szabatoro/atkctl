# Domain Glossary

## Project
**atkctl** — CLI + GUI tool for configuring ATK A9 PRO MAX 2.0 NK gaming mice (and compatible ATK/VXE/VGN models with BITMOUSE firmware).

## Protocol

| Term | Definition |
|------|------------|
| **BITMOUSE** | The HID protocol spoken by NK firmware. 64-byte frames on usage page `0xFF05`, report ID `0x08`. Full frame format in `src/atkctl/framing.py`. |
| **AtkDeviceProtocol** | Abstract interface (``typing.Protocol``) that all device consumers depend on. |
| **HidDevice** | Real HID implementation of the protocol. Opens ``hid.Device`` and sends BITMOUSE frames. |
| **FakeDevice** | In-memory fake implementing the same protocol, used in tests. Stores EEPROM in a bytearray. |
| **Slot** | `0x00` = wired (direct USB), `0x01` = wireless (mouse behind receiver). Auto-detected. |
| **Config block** | Active settings read via command `0x09`: polling rate, lift-off, debounce, sleep, motion sync, angle snap, ripple control. |
| **DPI block** | 70-byte structure (read as 7 × 10-byte EEPROM chunks from address 1) with 8 stages. Each stage: 8 bytes (X_lo, X_hi, Y_lo, Y_hi, B, G, R, reserved). |

## Commands

| Module | Concerns |
|--------|----------|
| `commands.py` | BITMOUSE command IDs, polling rate code maps, slot constants, EEPROM address map |
| `models.py` | ``BatteryStatus``, ``MouseInfo`` dataclasses, ``PanelData`` TypedDict, ``lift_off_description()`` |
| `framing.py` | ``build_request()``, ``parse_response()``, ``_calc_checksum()`` |
| `discovery.py`` | ``find_atk_hidraw5()``, ``enumerate_atk_interfaces()`` |
| `device.py` | ``AtkDeviceProtocol``, ``HidDevice``, ``FakeDevice``, ``create_device()`` |

## Architecture decisions

- **Abstract seam**: ``AtkDeviceProtocol`` is a ``typing.Protocol`` (not ABC) so consumers don't need explicit inheritance.
- **One adapter = hypothetical, two = real**: ``FakeDevice`` alongside ``HidDevice`` makes the seam load-bearing.
- **No udevadm fallback**: Device discovery uses only the ``hid`` library's enumeration. The previous udevadm+glob fallback was removed — see architecture review candidate #5.
- **read_all() is the authority**: The GUI worker no longer re-reads ``query_config()`` after ``read_all()``. The ``MouseInfo`` dataclass now includes ``lift_off_level`` so that value is available without a second query.
- **PanelData TypedDict**: The interface between worker and GUI panels is typed via ``PanelData`` in ``models.py``.