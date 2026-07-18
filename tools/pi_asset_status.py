
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modules.common.model_asset_truth import collect_asset_truth
parser = argparse.ArgumentParser()
parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[1]))
args = parser.parse_args()
status = collect_asset_truth(args.project_root)
print(json.dumps(status, ensure_ascii=False, indent=2))
raise SystemExit(0 if status.get("ok") else 2)
