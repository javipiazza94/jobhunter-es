"""Congela el backend con PyInstaller y deja `desktop/src-tauri/resources/jobhunter-api/`.

Uso: python desktop/scripts/freeze_backend.py [--dist DIR]
Requiere las dependencias de backend/requirements.txt y `pyinstaller` instalados en el Python que lo ejecuta.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "backend" / "desktop_freeze.spec"
DEFAULT_DIST = ROOT / "desktop" / "src-tauri" / "resources"


def freeze(dist: Path) -> Path:
    target = dist / "jobhunter-api"
    if target.exists():
        shutil.rmtree(target)
    with tempfile.TemporaryDirectory(prefix="jh-pyinstaller-") as work:
        subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
             "--distpath", str(dist), "--workpath", work, str(SPEC)],
            cwd=ROOT / "backend", check=True,
        )
    exe = target / ("jobhunter-api.exe" if sys.platform == "win32" else "jobhunter-api")
    if not exe.exists():
        raise SystemExit(f"PyInstaller no generó {exe}")
    return exe


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=DEFAULT_DIST)
    args = parser.parse_args()
    print(f"OK: {freeze(args.dist.resolve())}")


if __name__ == "__main__":
    main()
