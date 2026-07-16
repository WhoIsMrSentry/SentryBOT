from __future__ import annotations

from typing import Any, List


I2C_SCAN_CONTRACT = True
I2C_SCAN_BOUNDARY_ROLE = "pi_linux_safe_i2c_probe"
I2C_SCAN_UNAVAILABLE_BEHAVIOR = "return_empty_list"


def _load_smbus2() -> Any | None:
    try:
        import smbus2  # type: ignore
    except Exception:
        return None
    return smbus2


def _probe_address(bus_handle: Any, addr: int) -> bool:
    try:
        bus_handle.write_quick(addr)
        return True
    except Exception:
        return False


def scan(bus: int = 1) -> List[int]:
    """Return detected I2C addresses as integers.

    The function is safe to import on PC/dev hosts and Pi systems without I2C
    dependencies. Missing smbus2, missing permissions, or unavailable I2C bus
    return an empty list instead of pretending that hardware exists.
    """

    smbus2 = _load_smbus2()
    if smbus2 is None:
        return []

    found: List[int] = []
    handle = None
    try:
        handle = smbus2.SMBus(int(bus))
        for addr in range(0x03, 0x78):
            if _probe_address(handle, addr):
                found.append(addr)
    except Exception:
        return []
    finally:
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass
    return found
