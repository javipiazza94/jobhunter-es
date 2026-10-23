"""Comprueba que la versión es la misma en tauri.conf.json, Cargo.toml y package.json y, con --tag, que
coincide con el tag que se va a publicar (vX.Y.Z).

Uso: python desktop/scripts/check_version.py [--tag v0.1.0]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DESKTOP = Path(__file__).resolve().parents[1]


def versions(desktop: Path = DESKTOP) -> dict[str, str]:
    conf = json.loads((desktop / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))["version"]
    pkg = json.loads((desktop / "package.json").read_text(encoding="utf-8"))["version"]
    cargo_text = (desktop / "src-tauri" / "Cargo.toml").read_text(encoding="utf-8")
    package = re.search(r"^\[package\](.*?)(?=^\[)", cargo_text, re.S | re.M)
    match = re.search(r'^version\s*=\s*"([^"]+)"', package.group(1), re.M) if package else None
    if not match:
        raise SystemExit("No encuentro la versión en Cargo.toml")
    return {"tauri.conf.json": conf, "Cargo.toml": match.group(1), "package.json": pkg}


def check(found: dict[str, str], tag: str | None = None) -> list[str]:
    problems = []
    if len(set(found.values())) != 1:
        problems.append(f"Las versiones no coinciden: {found}")
    if tag is not None:
        expected = tag[1:] if tag.startswith("v") else tag
        bad = {k: v for k, v in found.items() if v != expected}
        if bad:
            problems.append(f"El tag {tag} no coincide con {bad}")
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag")
    args = parser.parse_args()
    found = versions()
    problems = check(found, args.tag)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        raise SystemExit(1)
    print(f"Versión {next(iter(found.values()))} coherente")


if __name__ == "__main__":
    main()
