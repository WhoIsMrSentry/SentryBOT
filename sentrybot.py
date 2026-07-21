#!/usr/bin/env python3
"""
SentryBOT Launcher
This script is the unified entry point for SentryBOT.
It displays the system information (neofetch style), waits briefly,
and then launches the advanced SentryBOT Control Center (htop style)
while simultaneously starting the robot's backend services.
"""

import sys
import time
import argparse
from modules.runtime_console.system_info_tui import main as sysinfo_main
from modules.runtime_console.tui_v2 import main as tui_main

def main():
    parser = argparse.ArgumentParser(description="SentryBOT Ultimate Launcher")
    parser.add_argument("--no-run", action="store_true", help="Do not start the robot backend, just open the TUI")
    # We parse known args so we can pass the rest to tui_v2 if needed
    args, unknown = parser.parse_known_args()

    # 1. Print Neofetch-style system info
    print("\n\x1b[1;36m--- SENTRYBOT SYSTEM INITIALIZING ---\x1b[0m\n")
    try:
        sysinfo_main(["--once"])
    except Exception as e:
        print(f"Error displaying system info: {e}")

    # 2. Wait slightly
    print("\n\x1b[2mLoading Control Center...\x1b[0m")
    time.sleep(2.5)

    # 3. Launch the htop-like TUI
    # We pass --run to start the background robot process (run_robot.py)
    # unless the user specified --no-run
    tui_args = ["--alt"]  # Use alternate screen for clean exit
    if not args.no_run:
        tui_args.append("--run")
    
    tui_args.extend(unknown)

    return tui_main(tui_args)

if __name__ == "__main__":
    sys.exit(main())
