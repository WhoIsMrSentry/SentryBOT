from __future__ import annotations
"""Quick CLI helper to manage Autonomy light palettes."""

import argparse
from pathlib import Path
from typing import List

from ..services.palette_store import CONFIG_PATH, list_palettes, set_palette, remove_palette


def _parse_hex(value: str) -> List[int]:
    stripped = value.strip().lstrip("#")
    if len(stripped) != 6 or any(c not in "0123456789abcdefABCDEF" for c in stripped):
        raise ValueError("Hex value must be like ff8800")
    r = int(stripped[0:2], 16)
    g = int(stripped[2:4], 16)
    b = int(stripped[4:6], 16)
    return [r, g, b]


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage Autonomy light palettes")
    parser.add_argument(
        "--config",
        type=Path,
        default=CONFIG_PATH,
        help="Path to autonomy config.yml (defaults to module config)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List available palettes")

    set_cmd = sub.add_parser("set", help="Add or update a palette")
    set_cmd.add_argument("name", help="Palette key (e.g. sunset_gold)")
    set_cmd.add_argument("--rgb", nargs=3, type=int, metavar=("R", "G", "B"))
    set_cmd.add_argument("--hex", type=str, help="Hex color like ff8800")

    rm_cmd = sub.add_parser("remove", help="Delete a palette")
    rm_cmd.add_argument("name", help="Palette key to remove")

    args = parser.parse_args()
    config_path = args.config

    if args.command == "list":
        for name, rgb in list_palettes(config_path).items():
            print(f"{name}: {tuple(rgb)}")
        return

    if args.command == "set":
        rgb = None
        if args.rgb:
            rgb = [int(v) for v in args.rgb]
        elif args.hex:
            rgb = _parse_hex(args.hex)
        if rgb is None:
            raise SystemExit("Provide --rgb R G B or --hex HEX")
        palettes = set_palette(args.name, rgb, config_path)
        print(f"Set palette '{args.name}' to {tuple(palettes[args.name])}")
        return

    if args.command == "remove":
        palettes = remove_palette(args.name, config_path)
        print(f"Removed palette '{args.name}'. Remaining: {', '.join(palettes.keys()) or 'none'}")
        return


if __name__ == "__main__":
    main()
