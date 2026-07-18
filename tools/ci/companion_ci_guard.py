import argparse
import py_compile
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable

DEFAULT_EXCLUDES = {".git", ".venv", "__pycache__", ".pytest_cache"}

def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except Exception:
        return str(path)

def iter_py_files():
    for p in ROOT.rglob("*.py"):
        parts = set(p.parts)
        if parts & DEFAULT_EXCLUDES:
            continue
        yield p

def print_rows(rows):
    print("case                     status   reason")
    print("------------------------------------------------------------------------------")
    for case, status, reason in rows:
        print(f"{case:<24} {status:<8} {reason}")

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-tests", action="store_true", help="Run full pytest suite under tests/.")
    args = ap.parse_args()
    rows = []
    passed = 0
    total = 0
    skipped = 0

    total += 1
    count = 0
    try:
        for f in iter_py_files():
            py_compile.compile(str(f), doraise=True)
            count += 1
        rows.append(("py_compile", "PASS", f"files={count} per_file_compile=True"))
        passed += 1
    except Exception as exc:
        rows.append(("py_compile", "FAIL", f"{type(exc).__name__}: {exc}"))

    total += 1
    tests_dir = ROOT / "tests"
    if not args.run_tests:
        rows.append(("pytest", "SKIP", "use --run-tests for full suite"))
        skipped += 1
    elif not tests_dir.exists():
        rows.append(("pytest", "SKIP", "root tests/ not found"))
        skipped += 1
    else:
        proc = subprocess.run([PYTHON, "-m", "pytest", "tests"], cwd=str(ROOT), text=True, capture_output=True)
        reason = (proc.stdout or proc.stderr or "").strip().splitlines()[-1] if (proc.stdout or proc.stderr).strip() else f"exit={proc.returncode}"
        if proc.returncode == 0:
            rows.append(("pytest", "PASS", reason))
            passed += 1
        else:
            rows.append(("pytest", "FAIL", reason))

    print_rows(rows)
    print() 
    effective = total - skipped
    print(f"summary: {passed}/{effective} passed, skipped={skipped}")
    return 0 if passed == effective else 1

if __name__ == "__main__":
    raise SystemExit(main())
