"""Tests for the device layer — using FakeDevice to avoid real HID hardware."""

from atkctl.commands import (
    POLLING_CODES,
    POLLING_CODES_REV,
    SLOT_WIRED,
    SLOT_WIRELESS,
)
from atkctl.device import FakeDevice, HidDevice
from atkctl.models import BatteryStatus, MouseInfo


# ── FakeDevice basics ────────────────────────────────────────────────


def test_fake_device_lifecycle():
    dev = FakeDevice()
    assert dev._open is False
    dev.open()
    assert dev._open is True
    dev.close()
    assert dev._open is False


def test_fake_device_context_manager():
    with FakeDevice() as dev:
        assert dev._open is True
    assert dev._open is False


def test_fake_device_path_and_slot():
    dev = FakeDevice()
    assert dev.path == "/dev/fake"
    assert dev.slot == SLOT_WIRELESS


# ── Queries ──────────────────────────────────────────────────────────


def test_fake_battery():
    dev = FakeDevice().open()
    bat = dev.query_battery()
    assert isinstance(bat, BatteryStatus)
    assert bat.level == 85
    assert bat.charging is False
    assert bat.voltage_mv == 3800


def test_fake_version():
    dev = FakeDevice().open()
    assert dev.query_version() == "1.0.0"


def test_fake_config():
    dev = FakeDevice().open()
    cfg = dev.query_config()
    assert cfg is not None
    assert cfg["polling_rate_hz"] == 1000
    assert cfg["lift_off_level"] == 4
    assert cfg["motion_sync"] is True
    assert cfg["debounce_ms"] == 4


def test_fake_dpi_block():
    dev = FakeDevice().open()
    block = dev.query_dpi_block()
    assert block is not None
    assert block["active_index"] == 0
    assert block["stage_count"] == 8
    assert len(block["stages"]) > 0
    assert block["stages"][0] == (400, 400)


def test_fake_dpi():
    dev = FakeDevice().open()
    active_dpi, stages, active = dev.query_dpi()
    assert active_dpi == 400
    assert stages is not None
    assert len(stages) > 0
    assert active == 0


def test_fake_polling_rate():
    dev = FakeDevice().open()
    assert dev.query_polling_rate() == 1000


def test_fake_lift_off():
    dev = FakeDevice().open()
    lo = dev.query_lift_off()
    assert lo is not None
    assert "mm" in lo
    assert "Medium" in lo


def test_fake_online():
    dev = FakeDevice().open()
    assert dev.query_online() is True


def test_fake_connection_type():
    dev = FakeDevice().open()
    assert dev.query_connection_type() == "Wireless (2.4GHz)"


def test_fake_wireless_mode():
    dev = FakeDevice().open()
    assert dev.query_wireless_mode() == "Connected"


def test_fake_dongle_led():
    dev = FakeDevice().open()
    assert dev.query_dongle_led() == "Battery level"


def test_fake_device_info():
    dev = FakeDevice().open()
    info = dev.query_device_info()
    assert info is not None
    assert info["raw"] == "060000"


# ── Writes ───────────────────────────────────────────────────────────


def test_fake_set_polling_rate():
    dev = FakeDevice().open()
    assert dev.set_polling_rate(0) is True
    assert dev.set_polling_rate(4) is True


def test_fake_set_debounce():
    dev = FakeDevice().open()
    assert dev.set_debounce(4) is True
    assert dev.set_debounce(0) is True
    assert dev.set_debounce(255) is True


def test_fake_set_motion_sync():
    dev = FakeDevice().open()
    assert dev.set_motion_sync(True) is True
    assert dev.set_motion_sync(False) is True


def test_fake_set_angle_snap():
    dev = FakeDevice().open()
    assert dev.set_angle_snap(True) is True
    assert dev.set_angle_snap(False) is True


def test_fake_set_ripple_control():
    dev = FakeDevice().open()
    assert dev.set_ripple_control(True) is True
    assert dev.set_ripple_control(False) is True


def test_fake_set_sleep_timeout():
    dev = FakeDevice().open()
    assert dev.set_sleep_timeout(60) is True
    assert dev.set_sleep_timeout(0) is True


def test_fake_set_lift_off():
    dev = FakeDevice().open()
    assert dev.set_lift_off(4) is True
    assert dev.set_lift_off(0) is True
    assert dev.set_lift_off(10) is True


def test_fake_set_dongle_light():
    dev = FakeDevice().open()
    assert dev.set_dongle_light(1) is True
    assert dev.set_dongle_light(0) is True


def test_fake_set_dpi():
    dev = FakeDevice().open()
    assert dev.set_dpi(0, 800, 800) is True
    assert dev.set_dpi(1, 1600, 1600, red=255, green=0, blue=0) is True


# ── Raw read ─────────────────────────────────────────────────────────


def test_fake_raw_read():
    dev = FakeDevice().open()
    assert dev.raw_read(64) == []


# ── EEPROM ───────────────────────────────────────────────────────────


def test_fake_eeprom_read_write():
    dev = FakeDevice().open()
    # Write then read back
    dev.write_eeprom(0x10, bytes([0xAB, 0xCD, 0xEF]))
    data = dev.read_eeprom(0x10, 3)
    assert data is not None
    assert data == bytes([0xAB, 0xCD, 0xEF])


def test_fake_eeprom_out_of_bounds():
    dev = FakeDevice().open()
    data = dev.read_eeprom(0x100, 10)
    assert data is None  # beyond 256-byte default buffer


def test_fake_eeprom_default_content():
    """Default EEPROM should be zeroed."""
    dev = FakeDevice().open()
    data = dev.read_eeprom(0, 4)
    assert data == bytes([0, 0, 0, 0])


# ── Bulk read (read_all) ─────────────────────────────────────────────


def test_fake_read_all():
    dev = FakeDevice().open()
    info = dev.read_all()
    assert isinstance(info, MouseInfo)
    assert info.battery is not None
    assert info.battery.level == 85
    assert info.version == "1.0.0"
    assert info.firmware == "1.0.0"
    assert info.polling_rate_hz == 1000
    assert info.lift_off_level == 4
    assert info.lift_off is not None
    assert "Medium" in info.lift_off
    assert info.debounce_ms == 4
    assert info.motion_sync is True
    assert info.angle_snap is False
    assert info.ripple_control is False
    assert info.sleep_timeout_s == 300
    assert info.dpi == 400
    assert len(info.dpi_stages) > 0
    assert info.connection_type == "Wireless (2.4GHz)"
    assert info.wireless_mode == "Connected"


# ── Protocol conformance ─────────────────────────────────────────────


def test_fake_conforms_to_protocol():
    from typing import cast
    from atkctl.device import AtkDeviceProtocol
    dev = cast(AtkDeviceProtocol, FakeDevice())
    assert isinstance(dev, AtkDeviceProtocol), "FakeDevice must satisfy AtkDeviceProtocol"


def test_hid_device_satisfies_protocol():
    """HidDevice satisfies AtkDeviceProtocol structurally.

    Walks the method signatures defined on the protocol and verifies
    HidDevice implements every one of them.
    """
    import inspect
    from atkctl.device import AtkDeviceProtocol, HidDevice

    # Get all public method names defined directly on the Protocol
    proto_methods = {}
    for name, value in AtkDeviceProtocol.__dict__.items():
        if not name.startswith("_") and callable(value):
            proto_methods[name] = inspect.signature(value)

    missing = []
    for name, sig in proto_methods.items():
        if not hasattr(HidDevice, name):
            missing.append(name)
        else:
            method = getattr(HidDevice, name)
            if not callable(method):
                missing.append(f"{name} (not callable)")

    assert not missing, (
        f"HidDevice is missing protocol methods: {missing}"
    )


# ── Model helpers ────────────────────────────────────────────────────


def test_lift_off_description():
    from atkctl.models import lift_off_description
    desc = lift_off_description(4)
    assert "1.0 mm" in desc
    assert "Medium" in desc


def test_lift_off_description_low():
    from atkctl.models import lift_off_description
    desc = lift_off_description(1)
    assert "0.7 mm" in desc
    assert "Low" in desc


def test_lift_off_description_high():
    from atkctl.models import lift_off_description
    desc = lift_off_description(11)
    assert "1.7 mm" in desc
    assert "High" in desc


def test_lift_off_description_unknown():
    from atkctl.models import lift_off_description
    desc = lift_off_description(7)
    assert "mm" in desc
    assert "Medium" not in desc
    assert "Low" not in desc
    assert "High" not in desc


# ── PanelData ────────────────────────────────────────────────────────


def test_mouse_info_to_panel_data():
    from atkctl.models import mouse_info_to_panel_data
    dev = FakeDevice().open()
    info = dev.read_all()
    pd = mouse_info_to_panel_data(info)
    assert pd.get("dpi") == 400
    assert pd.get("polling_rate_hz") == 1000
    assert pd.get("lift_off_level") == 4
    assert pd.get("battery") is not None
    assert pd["battery"]["level"] == 85


def test_mouse_info_to_panel_data_none():
    from atkctl.models import mouse_info_to_panel_data
    assert mouse_info_to_panel_data(None) == {}


# ── Polling codes ────────────────────────────────────────────────────


def test_polling_codes():
    assert POLLING_CODES[0] == 1000
    assert POLLING_CODES[1] == 500
    assert POLLING_CODES[4] == 8000
    assert POLLING_CODES_REV[1000] == 0
    assert POLLING_CODES_REV[8000] == 4