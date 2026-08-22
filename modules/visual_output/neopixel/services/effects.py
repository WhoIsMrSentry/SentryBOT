from __future__ import annotations
from typing import Tuple


def wheel(pos: int) -> Tuple[int, int, int]:
    # 0–255 -> RGB
    pos = int(pos) & 255
    if pos < 85:
        return (pos * 3, 255 - pos * 3, 0)
    elif pos < 170:
        pos -= 85
        return (255 - pos * 3, 0, pos * 3)
    else:
        pos -= 170
        return (0, pos * 3, 255 - pos * 3)
