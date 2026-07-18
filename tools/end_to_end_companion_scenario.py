
from __future__ import annotations
import argparse, json, requests
parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://127.0.0.1:8080")
args = parser.parse_args()
r = requests.post(args.base_url.rstrip("/") + "/autonomy/scenario/companion-e2e", json={"mode": "safe"}, timeout=5.0)
print(json.dumps(r.json(), ensure_ascii=False, indent=2))
raise SystemExit(0 if r.status_code == 200 else 2)
