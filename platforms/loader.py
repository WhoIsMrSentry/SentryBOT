from __future__ import annotations
import importlib
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Optional

from .detect import detect_platform


def prepend_platform_paths(platform: Optional[str] = None) -> str:
    """Prepend platform-specific paths to sys.path so that `modules` can be overridden.

    Directory layout:
    platforms/<platform>/modules/  -> shadows default modules/*
    platforms/<platform>/configs/  -> holds platform-specific config files
    """
    root = Path(__file__).resolve().parent.parent
    plat = platform or detect_platform()
    plat_root = root / "platforms" / plat
    plat_configs = plat_root / "configs"
    # Add platform root so that 'modules' package under it shadows default
    for p in [plat_root, plat_configs]:
        p_str = str(p)
        if p.exists() and p_str not in sys.path:
            sys.path.insert(0, p_str)
    return plat


def import_platform_module(module_name: str, platform: Optional[str] = None) -> ModuleType:
    """Import module, preferring platform override if present.

    Example: import_platform_module('modules.camera.xCameraService')
    """
    plat = prepend_platform_paths(platform)
    try:
        return importlib.import_module(module_name)
    except Exception:
        # Fallback to default import path
        return importlib.import_module(module_name)
