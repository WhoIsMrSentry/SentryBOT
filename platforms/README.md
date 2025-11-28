# Platforms override layer

This folder allows OS/hardware-specific overrides without modifying core modules.

Structure:
- platforms/<platform>/modules/...  # drop-in replacements that shadow default modules/*
- platforms/<platform>/configs/...  # platform-specific config files (optional)

Supported platform keys:
- windows
- rpi
- linux
- macos

At runtime, `run_robot.py` prepends the detected platform paths so imports like `modules.camera...` resolve to `platforms/<plat>/modules/camera...` if present, otherwise falling back to the default `modules/`.
