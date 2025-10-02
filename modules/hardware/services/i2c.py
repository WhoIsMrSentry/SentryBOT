from __future__ import annotations
from typing import List


def scan(bus: int = 1) -> List[int]:
    """Return detected I2C addresses (hex ints). Stub returns empty list on non-RPi systems."""
    try:
        import smbus2  # type: ignore
    except Exception:
        return []
    found: List[int] = []
    try:
        b = smbus2.SMBus(bus)
        for addr in range(0x03, 0x78):
            try:
                b.write_quick(addr)
                found.append(addr)
            except Exception:
                pass
        b.close()
    except Exception:
        return []
    return found
