
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modules.autonomy.services.pi_hardware_runtime import PiHardwareRuntime
parser = argparse.ArgumentParser()
parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[1]))
args = parser.parse_args()
old = Path.cwd(); os.chdir(Path(args.project_root).resolve())
try:
    status = PiHardwareRuntime().status()
finally:
    os.chdir(old)
print(json.dumps(status, ensure_ascii=False, indent=2))
raise SystemExit(0 if status.get("ok") else 2)
