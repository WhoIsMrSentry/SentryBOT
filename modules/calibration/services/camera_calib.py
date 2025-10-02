from __future__ import annotations
from typing import Dict, Any


def suggest_checkerboard(cols: int = 9, rows: int = 6, square_mm: float = 25.0) -> Dict[str, Any]:
    return {"cols": cols, "rows": rows, "square_mm": square_mm}
