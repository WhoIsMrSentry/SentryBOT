"""Canonical time parsing and window check utilities for SentryBOT."""
from __future__ import annotations

import re
from typing import Any, Optional, Tuple

_HHMM_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def parse_hhmm(value: Any) -> Optional[Tuple[int, int]]:
    """Parse 'HH:MM' string into (hour, minute) tuple. Returns None if invalid."""
    if not isinstance(value, str):
        return None
    match = _HHMM_RE.match(value.strip())
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return (hour, minute)
    return None


def is_time_in_window(current: Tuple[int, int], start: Tuple[int, int], end: Tuple[int, int]) -> bool:
    """Check if current (hh, mm) falls within [start, end], handling midnight crossover."""
    cur_m = current[0] * 60 + current[1]
    start_m = start[0] * 60 + start[1]
    end_m = end[0] * 60 + end[1]
    if start_m <= end_m:
        return start_m <= cur_m <= end_m
    # Midnight crossover (e.g., 23:00 to 07:00)
    return cur_m >= start_m or cur_m <= end_m


__all__ = ["parse_hhmm", "is_time_in_window"]

