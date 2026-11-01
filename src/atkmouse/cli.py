"""CLI interface for ATK mouse battery monitoring."""

import argparse
import json
import os
import sys
import time
from typing import Optional

import hid

from .protocol import (
    AtkDevice,
    BatteryStatus,
    CMD_BATTERY,
    POLLING_CODES,
    POLLING_CODES_REV,
    find_atk_hidraw5,
    enumerate_atk_interfaces,
    CMD_READ_EEPROM,
    lift_off_description,
)


def _resolve(specified: str | None) -> str | None:
    """Resolve device path from user-specified or auto-detect."""
    if specified:
        if os.path.exists(specified):
            return specified
        print(f"Device {specified} not found.", file=sys.stderr)
        return None
    return find_atk_hidraw5()


def _open(specified: Optional[str] = None) -> AtkDevice:
    path = _resolve(specified)
    if not path:
        print("No ATK device found. Use --device /dev/hidraw5", file=sys.stderr)
        sys.exit(1)
    return AtkDevice(path)


def cmd_battery(args: argparse.Namespace) -> None:
    """Read battery status once."""
    with _open(args.device) as dev:
        status = dev.query_battery()
        if status:
            if args.json:
                print(json.dumps({
                    "battery_level": status.level,
                    "charging": status.charging,
                    "voltage_mv": status.voltage_mv,
                }))
            else:
                chg = " (charging)" if status.charging else ""
                volt = f"  {status.voltage_mv} mV" if status.voltage_mv else ""
                print(f"Battery: {status.level}%{chg}{volt}")
        else:
            print("No battery data (mouse may be asleep).", file=sys.stderr)
            sys.exit(1)


def cmd_status(args: argparse.Namespace) -> None:
    """Read full device telemetry."""
    with _open(args.device) as dev:
        info = dev.read_all()

        if args.json:
            print(json.dumps({
                "path": info.path,
                "connection": info.connection_type,
                "wireless_mode": info.wireless_mode,
                "battery_level": info.battery.level if info.battery else None,
                "charging": info.battery.charging if info.battery else None,
                "voltage_mv": info.battery.voltage_mv if info.battery else None,
                "polling_rate_hz": info.polling_rate_hz,
                "dpi": info.dpi,
                "dpi_stages": info.dpi_stages,
                "active_dpi_stage": info.active_dpi_stage,
                "dpi_stage_count": info.dpi_stage_count,
                "lift_off": info.lift_off,
                "debounce_ms": info.debounce_ms,
                "motion_sync": info.motion_sync,
                "angle_snap": info.angle_snap,
                "sleep_timeout_s": info.sleep_timeout_s,
                "ripple_control": info.ripple_control,
                "firmware": info.firmware,
            }, indent=2))
            return

        print(f"ATK Mouse Telemetry")
        print(f"{'=' * 50}")
        print(f"  Device:        {info.path}")
        print(f"  Connection:    {info.connection_type or '?'}")
        if info.wireless_mode:
            print(f"  Wireless:      {info.wireless_mode}")
        if info.firmware:
            print(f"  Firmware:      {info.firmware}")

        print()
        print("── Battery ──")
        if info.battery:
            chg = "Charging" if info.battery.charging else "Discharging"
            volt = f",  {info.battery.voltage_mv} mV" if info.battery.voltage_mv else ""
            print(f"  Level:         {info.battery.level}%  ({chg}{volt})")
        else:
            print("  (no data — mouse may be asleep)")

        print()
        print("── Performance ──")
        if info.polling_rate_hz:
            pr = f"{info.polling_rate_hz} Hz"
            code = POLLING_CODES_REV.get(info.polling_rate_hz)
            if code is not None:
                pr += f"  (code 0x{code:02X})"
            print(f"  Polling rate:  {pr}")
        if info.dpi:
            stages = ", ".join(str(d) for d in info.dpi_stages) if info.dpi_stages else "?"
            print(f"  DPI:           {info.dpi}")
            print(f"  Active stage:  #{info.active_dpi_stage}  (stages: {stages})")
        if info.lift_off:
            print(f"  Lift-off:      {info.lift_off}")

        print()
        print("── Advanced ──")
        if info.debounce_ms is not None:
            print(f"  Debounce:      {info.debounce_ms} ms")
        if info.motion_sync is not None:
            print(f"  Motion Sync:   {'On' if info.motion_sync else 'Off'}")
        if info.angle_snap is not None:
            print(f"  Angle Snap:    {'On' if info.angle_snap else 'Off'}")
        if info.ripple_control is not None:
            print(f"  Ripple ctrl:   {'On' if info.ripple_control else 'Off'}")
        if info.sleep_timeout_s:
            print(f"  Auto sleep:    {info.sleep_timeout_s}s")


def cmd_monitor(args: argparse.Namespace) -> None:
    """Continuously monitor battery."""
    path = _resolve(args.device)
    if not path:
        print("No ATK device found.", file=sys.stderr)
        sys.exit(1)

    print(f"Monitoring {path}  (every {args.interval}s, Ctrl+C to stop)\n", flush=True)

    next_poll = 0.0
    while True:
        now = time.time()
        if now >= next_poll:
            try:
                with AtkDevice(path) as dev:
                    status = dev.query_battery()
                ts = time.strftime("%H:%M:%S")
                if status:
                    chg = " (chg)" if status.charging else ""
                    print(f"[{ts}] {chg} Battery: {status.level}%", flush=True)
                else:
                    print(f"[{ts}]  asleep", flush=True)
            except Exception as e:
                print(f"[{ts}]  FAILED {e}", file=sys.stderr, flush=True)
            next_poll = now + args.interval
        time.sleep(0.5)


def cmd_discover(args: argparse.Namespace) -> None:
    """Show HID interfaces and try queries."""
    print("Scanning for ATK devices...\n")

    interfaces = enumerate_atk_interfaces()
    if not interfaces:
        print("  No ATK devices found.")
        sys.exit(1)

    by_path: dict[str, list] = {}
    for iface in interfaces:
        by_path.setdefault(iface["path"], []).append(iface)

    for path, ifaces in by_path.items():
        print(f"  {path}")
        for i in ifaces:
            mark = " ← config" if i["usage_page"] == 0xFF05 else ""
            print(f"    page=0x{i['usage_page']:04X} usage=0x{i['usage']:04X}"
                  f"  iface={i['interface_number']}{mark}")

        # Try full readout on the config interface
        config_ifaces = [i for i in ifaces if i["usage_page"] == 0xFF05]
        if config_ifaces:
            try:
                with AtkDevice(path) as dev:
                    info = dev.read_all()
                print(f"    Connection:     {info.connection_type or '?'}")
                if info.battery:
                    chg = " (chg)" if info.battery.charging else ""
                    print(f"    Battery:        {info.battery.level}%{chg}")
                else:
                    print(f"    Battery:        (asleep)")
                if info.firmware:
                    print(f"    Firmware:       {info.firmware}")
                if info.polling_rate_hz:
                    print(f"    Polling rate:   {info.polling_rate_hz} Hz")
                if info.dpi:
                    print(f"    DPI:            {info.dpi}  (#{info.active_dpi_stage})")
                    print(f"    DPI stages:     {info.dpi_stages}")
                if info.lift_off:
                    print(f"    Lift-off:       {info.lift_off}")
                if info.debounce_ms is not None:
                    print(f"    Debounce:       {info.debounce_ms} ms")
                if info.motion_sync is not None:
                    print(f"    Motion Sync:    {'On' if info.motion_sync else 'Off'}")
                if info.angle_snap is not None:
                    print(f"    Angle Snap:     {'On' if info.angle_snap else 'Off'}")
                if info.ripple_control is not None:
                    print(f"    Ripple ctrl:    {'On' if info.ripple_control else 'Off'}")
                if info.sleep_timeout_s:
                    print(f"    Auto sleep:     {info.sleep_timeout_s}s")
            except Exception as e:
                print(f"    Error: {e}")
        print()


def cmd_debug(args: argparse.Namespace) -> None:
    """Dump raw HID traffic."""
    path = _resolve(args.device)
    if not path:
        print("No ATK device found.", file=sys.stderr)
        sys.exit(1)

    print(f"Debug on {path}. Ctrl+C to stop.\n")

    try:
        dev = hid.Device(path=path.encode() if isinstance(path, str) else path)
        dev.nonblocking = True
        count = 0
        while True:
            resp = dev.read(64)
            if resp:
                count += 1
                ts = time.strftime("%H:%M:%S.%f")[:-3]
                hex_str = " ".join(f"{b:02x}" for b in resp)

                if len(resp) > 7 and resp[5] == 0x07:
                    print(f"[{ts}] #{count:>4}  BAT {resp[7]}%  {hex_str}")
                elif len(resp) > 5 and resp[1] == 0x72:
                    print(f"[{ts}] #{count:>4}  cmd=0x{resp[5]:02X} len={resp[6]}  {hex_str}")
                else:
                    print(f"[{ts}] #{count:>4}  {hex_str}")
            time.sleep(0.01)
    except KeyboardInterrupt:
        print("\nStopped.")


def cmd_eeprom(args: argparse.Namespace) -> None:
    """Read raw EEPROM data from an address, or scan a range."""
    path = _resolve(args.device)
    if not path:
        print("No ATK device found.", file=sys.stderr)
        sys.exit(1)

    with AtkDevice(path) as dev:
        if args.scan is not None:
            # Scan a range of addresses, 10 bytes each
            end = args.scan
            step = 10
            for addr in range(args.address, end + 1, step):
                data = dev.read_eeprom(addr, min(10, args.length))
                if data:
                    hex_str = " ".join(f"{b:02x}" for b in data)
                    print(f"  0x{addr:04X}: {hex_str}")
                else:
                    print(f"  0x{addr:04X}: (no data)")
                time.sleep(1.0)  # let mouse settle between reads
            return

        data = dev.read_eeprom(args.address, args.length)
        if data is None:
            print(f"No data returned from EEPROM address 0x{args.address:04X}")
            sys.exit(1)

        hex_str = " ".join(f"{b:02x}" for b in data)
        ints = ", ".join(str(b) for b in data)
        print(f"EEPROM[0x{args.address:04X}] ({args.length} bytes):")
        print(f"  Hex:  {hex_str}")
        print(f"  Dec:  {ints}")

        # Try little-endian uint16 interpretation
        if len(data) >= 2:
            u16 = [data[i] | (data[i+1] << 8) for i in range(0, len(data) - 1, 2)]
            print(f"  u16 (LE): {u16}")


def cmd_set_polling(args: argparse.Namespace) -> None:
    """Set the mouse polling rate."""
    if args.code is None and args.hz is None:
        print("error: specify polling rate in Hz or with --code", file=sys.stderr)
        sys.exit(1)
    code = None
    if args.code is not None:
        code = args.code
        hz = POLLING_CODES.get(code)
        if hz is None:
            print(f"Unknown polling code {code}. Valid codes: 0-6", file=sys.stderr)
            sys.exit(1)
    else:
        hz = args.hz
        code = POLLING_CODES_REV.get(hz)
        if code is None:
            valid = sorted(POLLING_CODES_REV.keys())
            print(f"Unsupported polling rate {hz} Hz. Valid: {valid}", file=sys.stderr)
            sys.exit(1)

    with _open(args.device) as dev:
        ok = dev.set_polling_rate(code)
        if ok:
            print(f"OK Polling rate set to {hz} Hz (code {code})")
        else:
            print("FAILED Failed to set polling rate (no response from device)", file=sys.stderr)
            sys.exit(1)


def cmd_set_dpi(args: argparse.Namespace) -> None:
    """Set a DPI stage on the mouse, or just activate an existing one."""
    stage = args.stage
    if stage < 0 or stage > 7:
        print("Stage must be 0-7", file=sys.stderr)
        sys.exit(1)

    has_values = args.x_dpi is not None and args.y_dpi is not None

    with _open(args.device) as dev:
        if not has_values:
            # Activate-only: read existing X and Y values for this stage
            _, stages, _ = dev.query_dpi()
            if not stages or stage >= len(stages) or stages[stage] == (0, 0):
                print(f"Stage {stage} does not have DPI values configured.", file=sys.stderr)
                print("Specify X and Y DPI values to configure it.", file=sys.stderr)
                sys.exit(1)
            x_dpi, y_dpi = stages[stage]
        else:
            x_dpi = args.x_dpi
            y_dpi = args.y_dpi

        ok = dev.set_dpi(
            stage=stage,
            x_dpi=x_dpi,
            y_dpi=y_dpi,
            red=args.red,
            green=args.green,
            blue=args.blue,
            enable=not args.no_enable,
        )
        if ok:
            if has_values:
                enable_str = " → active" if not args.no_enable else ""
                print(f"OK DPI stage {stage}: X={x_dpi} Y={y_dpi}{enable_str}"
                      f"  (R={args.red} G={args.green} B={args.blue})")
            else:
                print(f"OK Activated DPI stage {stage} (X={x_dpi} Y={y_dpi})")
        else:
            print("FAILED Failed to set DPI stage (no response from device)", file=sys.stderr)
            sys.exit(1)


def _parse_bool(val: str) -> bool:
    """Parse on/off/1/0/true/false to bool."""
    low = val.lower()
    if low in ("on", "1", "true", "yes"):
        return True
    if low in ("off", "0", "false", "no"):
        return False
    raise ValueError(f"expected on/off/1/0, got {val!r}")


# Lift-off description imported from protocol.py
# Uses lift_off_description() — offset-calibration level = lift-off level - 1


DONGLE_LIGHT_MODES: dict[int, str] = {
    0: "Off",
    1: "Polling rate",
    2: "Battery level",
    3: "Low battery",
    4: "Effect 4",
    5: "Effect 5",
}


def _dongle_light_desc(mode: int) -> str:
    return DONGLE_LIGHT_MODES.get(mode, f"Mode {mode}")


# ── Setter CLI commands ──────────────────────────────────────

def cmd_set_debounce(args: argparse.Namespace) -> None:
    """Set debounce/stabilization time."""
    ms = args.ms
    if ms < 0 or ms > 255:
        print("Debounce must be 0-255 ms", file=sys.stderr)
        sys.exit(1)
    with _open(args.device) as dev:
        ok = dev.set_debounce(ms)
        if ok:
            print(f"OK Debounce set to {ms} ms")
        else:
            print("FAILED No response from device", file=sys.stderr)
            sys.exit(1)


def cmd_set_motion_sync(args: argparse.Namespace) -> None:
    """Toggle motion sync."""
    enabled = _parse_bool(args.state)
    with _open(args.device) as dev:
        ok = dev.set_motion_sync(enabled)
        if ok:
            print(f"OK Motion Sync: {'On' if enabled else 'Off'}")
        else:
            print("FAILED No response from device", file=sys.stderr)
            sys.exit(1)


def cmd_set_angle_snap(args: argparse.Namespace) -> None:
    """Toggle angle snapping."""
    enabled = _parse_bool(args.state)
    with _open(args.device) as dev:
        ok = dev.set_angle_snap(enabled)
        if ok:
            print(f"OK Angle Snap: {'On' if enabled else 'Off'}")
        else:
            print("FAILED No response from device", file=sys.stderr)
            sys.exit(1)


def cmd_set_ripple(args: argparse.Namespace) -> None:
    """Toggle ripple control."""
    enabled = _parse_bool(args.state)
    with _open(args.device) as dev:
        ok = dev.set_ripple_control(enabled)
        if ok:
            print(f"OK Ripple Control: {'On' if enabled else 'Off'}")
        else:
            print("FAILED No response from device", file=sys.stderr)
            sys.exit(1)


def cmd_set_sleep(args: argparse.Namespace) -> None:
    """Set auto-sleep timeout."""
    seconds = args.seconds
    if seconds < 0:
        print("Sleep timeout must be 0 or more seconds", file=sys.stderr)
        sys.exit(1)
    with _open(args.device) as dev:
        ok = dev.set_sleep_timeout(seconds)
        if ok:
            desc = " (disabled)" if seconds == 0 else f" ({seconds // 60}m {seconds % 60}s)"
            print(f"OK Auto-sleep timeout: {seconds}s{desc}")
        else:
            print("FAILED No response from device", file=sys.stderr)
            sys.exit(1)


def cmd_set_liftoff(args: argparse.Namespace) -> None:
    """Set lift-off distance."""
    level = args.level
    if level < 0 or level > 10:
        print("Lift-off level must be 0-10", file=sys.stderr)
        sys.exit(1)
    with _open(args.device) as dev:
        ok = dev.set_lift_off(level)
        if ok:
            # lift_off_description expects lift-off level = offset_calibration + 1
            print(f"OK Lift-off: level {level}  ({lift_off_description(level + 1)})")
        else:
            print("FAILED No response from device", file=sys.stderr)
            sys.exit(1)


def cmd_set_dongle_light(args: argparse.Namespace) -> None:
    """Set dongle LED mode."""
    mode = args.mode
    if mode < 0 or mode > 255:
        print("Mode must be 0-255", file=sys.stderr)
        sys.exit(1)
    with _open(args.device) as dev:
        ok = dev.set_dongle_light(mode)
        if ok:
            print(f"OK Dongle LED: mode {mode}  ({_dongle_light_desc(mode)})")
        else:
            print("FAILED No response from device", file=sys.stderr)
            sys.exit(1)


def _help_on_missing(parser: argparse.ArgumentParser, msg: str) -> None:
    """Print parser help + error to stderr, then exit."""
    parser.print_help(file=sys.stderr)
    print(f"\nerror: {msg}", file=sys.stderr)
    sys.exit(2)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ATK Mouse — query and configure ATK A9 PRO MAX / VXE / VGN gaming mice"
    )

    sub = parser.add_subparsers(dest="command", prog="atkmouse")

    # ── battery ───────────────────────────────────────────────────────
    p = sub.add_parser(
        "battery",
        help="Read battery level once",
        description=(
            "Read the battery level from the mouse. Also serves as a "
            "wake-up call if the mouse is in power-saving sleep mode."
        ),
    )
    p.add_argument("--json", action="store_true",
                   help="Output as JSON instead of human-readable text")
    p.add_argument("--device", "-d", metavar="PATH",
                   help="HID device path (e.g. /dev/hidraw5). Auto-detected if omitted")

    # ── status ────────────────────────────────────────────────────────
    p = sub.add_parser(
        "status",
        help="Read full device telemetry",
        description=(
            "Show all known telemetry: battery, connection, firmware, "
            "polling rate, DPI stages, lift-off, debounce, motion sync, "
            "angle snap, ripple control, and sleep timeout."
        ),
    )
    p.add_argument("--json", action="store_true",
                   help="Output as JSON instead of human-readable text")
    p.add_argument("--device", "-d", metavar="PATH",
                   help="HID device path. Auto-detected if omitted")

    # ── monitor ───────────────────────────────────────────────────────
    p = sub.add_parser(
        "monitor",
        help="Monitor battery continuously",
        description=(
            "Poll battery level at a regular interval and print each "
            "reading with a timestamp. Press Ctrl+C to stop."
        ),
    )
    p.add_argument("--device", "-d", metavar="PATH",
                   help="HID device path. Auto-detected if omitted")
    p.add_argument("--interval", "-i", type=int, default=60, metavar="SECONDS",
                   help="Seconds between polls (default: 60)")

    # ── discover ──────────────────────────────────────────────────────
    p = sub.add_parser(
        "discover",
        help="Discover and show device info",
        description=(
            "List all HID interfaces for ATK devices (VID 0x373b), "
            "identify the config interface (usage page 0xFF05), and "
            "attempt a full readout on each device found."
        ),
    )
    p.add_argument("--device", "-d", metavar="PATH",
                   help="HID device path. Auto-detected if omitted")

    # ── debug ─────────────────────────────────────────────────────────
    p = sub.add_parser(
        "debug",
        help="Dump raw HID traffic",
        description=(
            "Enter a live hex dump of all incoming HID reports from the "
            "config interface. Annotates battery responses and command "
            "replies. Press Ctrl+C to stop."
        ),
    )
    p.add_argument("--device", "-d", metavar="PATH",
                   help="HID device path. Auto-detected if omitted")

    # ── eeprom ────────────────────────────────────────────────────────
    p = sub.add_parser(
        "eeprom",
        help="Read raw EEPROM data",
        description=(
            "Read bytes from arbitrary EEPROM addresses on the device. "
            "Addresses are in the NK firmware layout (see docs/PROTOCOL.md "
            "for the EEPROM map). Use --scan to dump a range."
        ),
    )
    p.add_argument("address", type=lambda x: int(x, 0), metavar="ADDR",
                   help="EEPROM address in hex (e.g. 0x0001)")
    p.add_argument("--length", "-l", type=int, default=10, metavar="BYTES",
                   help="Number of bytes to read (default: 10)")
    p.add_argument("--scan", "-s", type=lambda x: int(x, 0), default=None,
                   metavar="END_ADDR",
                   help="End address for bulk scan (reads 10-byte blocks from ADDR to END_ADDR)")
    p.add_argument("--device", "-d", metavar="PATH",
                   help="HID device path. Auto-detected if omitted")

    # ── set-polling ───────────────────────────────────────────────────
    p = sub.add_parser(
        "set-polling",
        help="Set polling rate",
        description=(
            "Change the mouse sensor polling rate. Accepts a frequency "
            "in Hz (e.g. 1000 for 1 kHz) or a raw BITMOUSE code via "
            "--code. The mouse will re-read this value from EEPROM on "
            "next power-on."
        ),
        epilog=(
            "Examples:\n"
            "  atkmouse set-polling 1000\n"
            "  atkmouse set-polling --code 0\n"
            "\n"
            "Hz values: 125, 250, 500, 1000, 2000, 4000, 8000\n"
            "Codes: 0=1000  1=500  2=250  3=125  4=8000  5=4000  6=2000"
        ),
    )
    p.add_argument("hz", type=int, nargs="?", default=None, metavar="HZ",
                   help="Polling rate in Hz. One of: 125, 250, 500, 1000, 2000, 4000, 8000")
    p.add_argument("--code", "-c", type=int, default=None, metavar="CODE",
                   help="BITMOUSE polling code directly (0-6). Overrides HZ when set")
    p.add_argument("--device", "-d", metavar="PATH",
                   help="HID device path. Auto-detected if omitted")

    # ── set-dpi ───────────────────────────────────────────────────────
    p = sub.add_parser(
        "set-dpi",
        help="Set or activate a DPI stage",
        description=(
            "Write a DPI stage with X/Y resolution and LED colour, or "
            "just re-activate an already-configured stage by omitting "
            "the DPI values."
        ),
        epilog=(
            "Examples:\n"
            "  atkmouse set-dpi 0 3000 3000          # set stage 0, make active\n"
            "  atkmouse set-dpi 2                    # activate existing stage 2\n"
            "  atkmouse set-dpi 1 2000 2000 --no-enable --green 255"
        ),
    )
    p.add_argument("stage", type=int, metavar="STAGE",
                   help="Stage index (0-7)")
    p.add_argument("x_dpi", type=int, nargs="?", default=None, metavar="X_DPI",
                   help="X-axis DPI value. Omit to read existing and just activate")
    p.add_argument("y_dpi", type=int, nargs="?", default=None, metavar="Y_DPI",
                   help="Y-axis DPI value. Omit to read existing and just activate")
    p.add_argument("--red", type=int, default=255, metavar="0-255",
                   help="Red LED value (default: 255)")
    p.add_argument("--green", type=int, default=0, metavar="0-255",
                   help="Green LED value (default: 0)")
    p.add_argument("--blue", type=int, default=0, metavar="0-255",
                   help="Blue LED value (default: 0)")
    p.add_argument("--no-enable", action="store_true",
                   help="Store the stage without making it active")
    p.add_argument("--device", "-d", metavar="PATH",
                   help="HID device path. Auto-detected if omitted")

    # ── set-debounce ──────────────────────────────────────────────────
    p = sub.add_parser(
        "set-debounce",
        help="Set debounce / stabilisation time",
        description=(
            "Set the stabilisation (debounce) time in milliseconds. "
            "Higher values reduce unintended pointer movement when "
            "lifting the mouse off the surface."
        ),
        epilog="Example:  atkmouse set-debounce 4",
    )
    p.add_argument("ms", type=int, metavar="MS",
                   help="Debounce time in milliseconds (0-255)")
    p.add_argument("--device", "-d", metavar="PATH",
                   help="HID device path. Auto-detected if omitted")

    # ── set-motion-sync ───────────────────────────────────────────────
    p = sub.add_parser(
        "set-motion-sync",
        help="Toggle motion sync",
        description=(
            "Enable or disable motion synchronisation. Motion sync "
            "ties the X and Y axes together so the sensor behaves "
            "more predictably during fast flicks."
        ),
        epilog="Example:  atkmouse set-motion-sync on",
    )
    p.add_argument("state", type=str, choices=["on", "off"], metavar="{on,off}",
                   help="on or off")
    p.add_argument("--device", "-d", metavar="PATH",
                   help="HID device path. Auto-detected if omitted")

    # ── set-angle-snap ────────────────────────────────────────────────
    p = sub.add_parser(
        "set-angle-snap",
        help="Toggle angle snapping (linear correction)",
        description=(
            "Enable or disable angle snapping (also called linear "
            "correction). When on, the sensor snaps the cursor angle "
            "to the nearest 45-degree increment at low speeds."
        ),
        epilog="Example:  atkmouse set-angle-snap off",
    )
    p.add_argument("state", type=str, choices=["on", "off"], metavar="{on,off}",
                   help="on or off")
    p.add_argument("--device", "-d", metavar="PATH",
                   help="HID device path. Auto-detected if omitted")

    # ── set-ripple ────────────────────────────────────────────────────
    p = sub.add_parser(
        "set-ripple",
        help="Toggle ripple control",
        description=(
            "Enable or disable ripple control. Ripple control filters "
            "out high-frequency vibrations from the sensor surface."
        ),
        epilog="Example:  atkmouse set-ripple on",
    )
    p.add_argument("state", type=str, choices=["on", "off"], metavar="{on,off}",
                   help="on or off")
    p.add_argument("--device", "-d", metavar="PATH",
                   help="HID device path. Auto-detected if omitted")

    # ── set-sleep ─────────────────────────────────────────────────────
    p = sub.add_parser(
        "set-sleep",
        help="Set auto-sleep timeout",
        description=(
            "Set how long the mouse waits without movement before "
            "entering power-saving sleep mode. Set to 0 to disable "
            "auto-sleep (not recommended for battery-powered use)."
        ),
        epilog=(
            "Examples:\n"
            "  atkmouse set-sleep 60       # 1 minute\n"
            "  atkmouse set-sleep 0        # never sleep"
        ),
    )
    p.add_argument("seconds", type=int, metavar="SECONDS",
                   help="Timeout in seconds (0 = never sleep)")
    p.add_argument("--device", "-d", metavar="PATH",
                   help="HID device path. Auto-detected if omitted")

    # ── set-liftoff ───────────────────────────────────────────────────
    p = sub.add_parser(
        "set-liftoff",
        help="Set lift-off distance",
        description=(
            "Set the distance the mouse must be lifted before the "
            "sensor stops tracking (silent height / offset calibration). "
            "Level 1 ≈ 0.7 mm, level 4 ≈ 1.0 mm, level 10 ≈ 1.7 mm."
        ),
        epilog=(
            "Examples:\n"
            "  atkmouse set-liftoff 4   # Medium (1.0 mm)\n"
            "  atkmouse set-liftoff 1   # Low (0.7 mm)"
        ),
    )
    p.add_argument("level", type=int, metavar="LEVEL",
                   help="Offset calibration level 0-10 (0=min height, 10=max height)")
    p.add_argument("--device", "-d", metavar="PATH",
                   help="HID device path. Auto-detected if omitted")

    # ── set-dongle-light ──────────────────────────────────────────────
    p = sub.add_parser(
        "set-dongle-light",
        help="Set dongle LED mode",
        description=(
            "Change the LED behaviour on the wireless receiver dongle. "
            "Mode 0 turns the LED off; modes 1-3 follow different "
            "device status signals."
        ),
        epilog=(
            "Examples:\n"
            "  atkmouse set-dongle-light 0   # Off\n"
            "  atkmouse set-dongle-light 1   # Follows polling rate"
        ),
    )
    p.add_argument("mode", type=int, metavar="MODE",
                   help="LED mode (0=Off, 1=Polling rate, 2=Battery level, 3=Low battery)")
    p.add_argument("--device", "-d", metavar="PATH",
                   help="HID device path. Auto-detected if omitted")

    # ── Patch every subparser to show help on missing args ───────────
    for _name, _p in sub.choices.items():
        _p.error = lambda msg, _parser=_p: _help_on_missing(_parser, msg)

    args = parser.parse_args()

    _DISPATCH: dict[str, object] = {
        "battery": cmd_battery,
        "status": cmd_status,
        "monitor": cmd_monitor,
        "discover": cmd_discover,
        "debug": cmd_debug,
        "eeprom": cmd_eeprom,
        "set-polling": cmd_set_polling,
        "set-dpi": cmd_set_dpi,
        "set-debounce": cmd_set_debounce,
        "set-motion-sync": cmd_set_motion_sync,
        "set-angle-snap": cmd_set_angle_snap,
        "set-ripple": cmd_set_ripple,
        "set-sleep": cmd_set_sleep,
        "set-liftoff": cmd_set_liftoff,
        "set-dongle-light": cmd_set_dongle_light,
    }
    handler = _DISPATCH.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()