# atkmouse

Linux battery monitor and config tool for **ATK A9 PRO MAX 2.0 NK** gaming mice (and compatible ATK/VXE/VGN models with BITMOUSE firmware).

Communicates over USB HID using the reverse-engineered BITMOUSE protocol on usage page `0xFF05` (report ID `0x08`).

## Quick Start

```bash
# Install udev rules (one-time; unplug/replug after)
sudo cp udev/99-atk-mouse.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger

# Read battery once
uv run atkmouse battery

# Monitor continuously
uv run atkmouse monitor
```

## Commands

| Command | Description |
|---------|-------------|
| `atkmouse battery` | Read battery level once |
| `atkmouse status`  | Full telemetry dump (battery, polling, DPI, lift-off, settings) |
| `atkmouse monitor` | Continuous battery polling |
| `atkmouse discover` | Scan and show all ATK HID interfaces |
| `atkmouse debug`   | Raw HID traffic hex dump |
| `atkmouse eeprom`  | Read EEPROM addresses or scan a range |
| `atkmouse set-polling` | Set polling rate (Hz or BITMOUSE code) |
| `atkmouse set-dpi` | Write or activate a DPI stage |
| `atkmouse set-debounce` | Set stabilization time (ms) |
| `atkmouse set-motion-sync` | Toggle motion sync |
| `atkmouse set-angle-snap` | Toggle angle snapping |
| `atkmouse set-ripple` | Toggle ripple control |
| `atkmouse set-sleep` | Set auto-sleep timeout |
| `atkmouse set-liftoff` | Set lift-off distance |
| `atkmouse set-dongle-light` | Set dongle LED mode |

Use `atkmouse <command> --help` for per-command options. Add `--device /dev/hidrawN` if auto-detection doesn't find the right path.

## Installation

### Arch Linux (pacman)

```bash
# Build from the repo
makepkg -si
```

### From source

```bash
uv run atkmouse battery
```

### udev rules

The udev rule at `udev/99-atk-mouse.rules` grants world-accessible permissions to the ATK mouse HID interface. Without it you'll need root:

```bash
sudo cp udev/99-atk-mouse.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
```

## Project Structure

| Path | Description |
|------|-------------|
| `src/atkmouse/` | Python package source |
| `src/atkmouse/protocol.py` | BITMOUSE protocol — `AtkDevice` class, all query/command methods |
| `src/atkmouse/cli.py` | CLI entry point and all subcommands |
| `docs/PROTOCOL.md` | Full protocol documentation (frame format, commands, DPI block) |
| `udev/99-atk-mouse.rules` | udev rules for device access |
| `PKGBUILD` | Arch Linux package definition |

## Credits

Protocol researched by sniffing [ATK HUB](https://hub.atk.pro/) WebHID traffic. Canonical reference:

- [OpenMouse mouse-protocol](https://github.com/OpenMouse-Project/mouse-protocol) — BITMOUSE codec and ATK WebHID driver