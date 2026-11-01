# atkctl

Linux battery monitor and config tool for **ATK A9 PRO MAX 2.0 NK** gaming mice (and compatible ATK/VXE/VGN models with BITMOUSE firmware).

Communicates over USB HID using the reverse-engineered BITMOUSE protocol on usage page `0xFF05` (report ID `0x08`).

## Quick Start

```bash
# Install udev rules (one-time; unplug/replug after)
sudo cp udev/99-atkctl-mouse.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger

# Read battery once
uv run atkctl battery

# Monitor continuously
uv run atkctl monitor
```

## Commands

| Command | Description |
|---------|-------------|
| `atkctl battery` | Read battery level once |
| `atkctl status`  | Full telemetry dump (battery, polling, DPI, lift-off, settings) |
| `atkctl monitor` | Continuous battery polling |
| `atkctl discover` | Scan and show all ATK HID interfaces |
| `atkctl debug`   | Raw HID traffic hex dump |
| `atkctl eeprom`  | Read EEPROM addresses or scan a range |
| `atkctl set-polling` | Set polling rate (Hz or BITMOUSE code) |
| `atkctl set-dpi` | Write or activate a DPI stage |
| `atkctl set-debounce` | Set stabilization time (ms) |
| `atkctl set-motion-sync` | Toggle motion sync |
| `atkctl set-angle-snap` | Toggle angle snapping |
| `atkctl set-ripple` | Toggle ripple control |
| `atkctl set-sleep` | Set auto-sleep timeout |
| `atkctl set-liftoff` | Set lift-off distance |
| `atkctl set-dongle-light` | Set dongle LED mode |

Use `atkctl <command> --help` for per-command options. Add `--device /dev/hidrawN` if auto-detection doesn't find the right path.

## Installation

### Arch Linux (pacman)

```bash
# Build from the repo
makepkg -si
```

### From source

```bash
uv run atkctl battery
```

### udev rules

The udev rule at `udev/99-atkctl-mouse.rules` grants access to users physically at the system's console (via `TAG+="uaccess"` / systemd-logind ACL). Without it you'll need root:

```bash
sudo cp udev/99-atkctl-mouse.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
```

## Project Structure

| Path | Description |
|------|-------------|
| `src/atkctl/` | Python package source |
| `src/atkctl/protocol.py` | BITMOUSE protocol — `AtkDevice` class, all query/command methods |
| `src/atkctl/cli.py` | CLI entry point and all subcommands |
| `docs/PROTOCOL.md` | Full protocol documentation (frame format, commands, DPI block) |
| `udev/99-atkctl-mouse.rules` | udev rules for device access |
| `PKGBUILD` | Arch Linux package definition |

## Credits

Protocol researched by sniffing [ATK HUB](https://hub.atk.pro/) WebHID traffic. Canonical reference:

- [OpenMouse mouse-protocol](https://github.com/OpenMouse-Project/mouse-protocol) — BITMOUSE codec and ATK WebHID driver