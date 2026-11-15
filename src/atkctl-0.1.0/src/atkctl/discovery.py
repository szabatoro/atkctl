"""Device discovery — find ATK mouse HID interfaces.

Uses the ``hid`` library's enumeration. The udevadm/glob fallback
was removed because the HID API covers all cases — see architecture
review candidate #5.
"""

from typing import Optional

import hid


def find_atk_hidraw5() -> Optional[str]:
    """Find the hidraw path for the ATK config interface (usage page 0xFF05).

    Returns the device path (e.g. ``/dev/hidraw5``) or ``None``.
    """
    try:
        for d in hid.enumerate():
            if (
                d.get("vendor_id") == 0x373b
                and d.get("usage_page") == 0xFF05
                and d.get("usage") == 0x0001
            ):
                path = d.get("path", b"")
                if path:
                    return path.decode() if isinstance(path, bytes) else path
    except Exception:
        pass
    return None


def enumerate_atk_interfaces() -> list[dict]:
    """List every HID interface for ATK devices (VID 0x373b)."""
    interfaces: list[dict] = []
    try:
        for d in hid.enumerate():
            if d.get("vendor_id") == 0x373b:
                path = d.get("path", b"")
                interfaces.append(
                    {
                        "path": (
                            path.decode() if isinstance(path, bytes) else str(path)
                        ),
                        "usage_page": d["usage_page"],
                        "usage": d["usage"],
                        "interface_number": d.get("interface_number", -1),
                        "product": d.get("product_string", ""),
                    }
                )
    except Exception:
        pass
    return interfaces