#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

IGNORES = {".git", ".venv", "venv", "env", "__pycache__", "build", "dist", ".mypy_cache", ".ruff_cache", ".pytest_cache", ".vscode", "node_modules"}


def find_requirements(root: Path) -> List[Path]:
    """Find all requirements.txt files under root, preferring root/requirements.txt first."""
    reqs: List[Path] = []
    root_req = root / "requirements.txt"
    if root_req.exists():
        reqs.append(root_req)

    # Walk once to honor ignore folders
    for p in root.rglob("requirements.txt"):
        try:
            # Skip the one at root already added
            if p.resolve() == root_req.resolve():
                continue
        except Exception:
            if str(p) == str(root_req):
                continue
        if any(part in IGNORES for part in p.parts):
            continue
        reqs.append(p)

    # De-duplicate while preserving order
    seen = set()
    unique: List[Path] = []
    for p in reqs:
        rp = str(p.resolve()) if p.exists() else str(p)
        if rp in seen:
            continue
        seen.add(rp)
        unique.append(p)
    return unique


def label_for(req: Path, repo_root: Path) -> str:
    """Return a friendly label for printing (e.g., 'camera' or 'root')."""
    try:
        rel = req.parent.relative_to(repo_root)
    except Exception:
        rel = req.parent
    parts = list(rel.parts)
    if len(parts) >= 2 and parts[0] == "modules":
        return parts[1]
    if len(parts) == 0:
        return "root"
    return parts[-1] or "root"


def setup_venv(venv_path: Path) -> bool:
    """Create virtual environment if it doesn't exist."""
    if venv_path.exists():
        print(f"Virtual environment zaten mevcut: {venv_path}")
        return True
    
    print(f"Virtual environment oluşturuluyor: {venv_path}")
    result = subprocess.run([sys.executable, "-m", "venv", str(venv_path)], 
                          capture_output=True, text=True)
    if result.returncode != 0:
        print(f"HATA: Virtual environment oluşturulamadı: {result.stderr}")
        return False
    print("Virtual environment başarıyla oluşturuldu.")
    return True


def get_venv_python(venv_path: Path) -> str:
    """Get the Python executable path from virtual environment."""
    if os.name == 'nt':  # Windows
        return str(venv_path / "Scripts" / "python.exe")
    else:  # Unix/Linux
        return str(venv_path / "bin" / "python")


def install_requirements(files: Iterable[Path], dry_run: bool = False, pip_args: str | None = None, 
                        fail_fast: bool = False, use_venv: bool = False, venv_path: Path | None = None) -> List[Tuple[Path, int]]:
    results: List[Tuple[Path, int]] = []
    
    # Determine Python executable
    if use_venv and venv_path:
        python_exe = get_venv_python(venv_path)
        if not Path(python_exe).exists():
            print(f"HATA: Virtual environment Python bulunamadı: {python_exe}")
            return [(f, 1) for f in files]
    else:
        python_exe = sys.executable
    
    pip = [python_exe, "-m", "pip", "install", "-r"]
    extra = shlex.split(pip_args) if pip_args else []
    
    for f in files:
        lab = label_for(f, Path.cwd())
        venv_info = f" (venv: {venv_path.name})" if use_venv and venv_path else ""
        print(f"\n=== {lab} gereklilikleri kuruluyor ({f}){venv_info} ===")
        
        if dry_run:
            print(f"DRY-RUN: {python_exe} -m pip install -r {f} {' '.join(extra)}")
            results.append((f, 0))
            continue
            
        cmd = pip + [str(f)] + extra
        proc = subprocess.run(cmd, stdout=sys.stdout, stderr=sys.stderr, cwd=str(Path.cwd()))
        code = int(proc.returncode or 0)
        results.append((f, code))
        
        if code != 0:
            print(f"HATA: {f} kurulumu {code} kodu ile başarısız.")
            if fail_fast:
                break
                
    return results


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Tüm requirements.txt dosyalarını bulup kurar.")
    ap.add_argument("--only", nargs="*", default=None, help="Sadece belirtilen modülleri kur (ör. camera speech).")
    ap.add_argument("--skip", nargs="*", default=None, help="Belirtilen modülleri atla.")
    ap.add_argument("--dry-run", action="store_true", help="Yükleme komutlarını sadece yazdır.")
    ap.add_argument("--pip-args", default=None, help="pip için ekstra argümanlar (ör. --upgrade --no-cache-dir).")
    ap.add_argument("--fail-fast", action="store_true", help="İlk hata sonrası dur.")
    ap.add_argument("--use-venv", action="store_true", help="Virtual environment kullan.")
    ap.add_argument("--venv-path", default=".venv", help="Virtual environment yolu (varsayılan: .venv).")
    ap.add_argument("--break-system-packages", action="store_true", help="Sistem paketlerini kırmaya zorla (riskli).")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parent
    print(f"Geçerli dizin: {repo_root}")
    
    # Virtual environment setup
    venv_path = None
    if args.use_venv:
        venv_path = repo_root / args.venv_path
        if not setup_venv(venv_path):
            return 1

    all_reqs = find_requirements(repo_root)
    if not all_reqs:
        print("requirements.txt bulunamadı.")
        return 0

    # Filter by only/skip
    def _keep(p: Path) -> bool:
        lab = label_for(p, repo_root)
        if args.only:
            return lab in args.only or p.name in args.only
        if args.skip:
            return not (lab in args.skip or p.name in args.skip)
        return True

    selected = [p for p in all_reqs if _keep(p)]

    print("Bulunan requirements dosyaları:")
    for p in selected:
        print(f" - {label_for(p, repo_root)} -> {p}")

    # Add --break-system-packages if requested
    pip_args = args.pip_args or ""
    if args.break_system_packages and not args.use_venv:
        pip_args += " --break-system-packages"

    results = install_requirements(
        selected, 
        dry_run=args.dry_run, 
        pip_args=pip_args, 
        fail_fast=args.fail_fast,
        use_venv=args.use_venv,
        venv_path=venv_path
    )

    failed = [str(p) for p, code in results if code != 0]
    if failed:
        print("\nBazı kurulumlar başarısız oldu:")
        for f in failed:
            print(f" - {f}")
        return 1
    print("\nTüm gereklilikler başarıyla işlendi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())