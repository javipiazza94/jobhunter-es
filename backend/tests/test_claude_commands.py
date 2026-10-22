"""Test para validar que los comandos y agentes de Claude Code (.claude/commands y .claude/agents)
apuntan a rutas existentes, módulos Python importables y no referencian artefactos obsoletos.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLAUDE_DIR = REPO_ROOT / ".claude"
COMMANDS_DIR = CLAUDE_DIR / "commands"
AGENTS_DIR = CLAUDE_DIR / "agents"


def get_markdown_files() -> list[Path]:
    files = list(COMMANDS_DIR.glob("*.md")) + list(AGENTS_DIR.glob("*.md"))
    assert files, "No se encontraron archivos markdown en .claude/commands o .claude/agents"
    return files


def test_no_obsolete_artifacts_in_claude():
    """Ningún comando ni agente debe referenciar 'seen_jobs.json' ni 'salary_lookup'."""
    all_files = list(CLAUDE_DIR.rglob("*.md"))
    for file_path in all_files:
        content = file_path.read_text(encoding="utf-8")
        assert "seen_jobs.json" not in content, f"{file_path} todavía referencia 'seen_jobs.json'"
        assert "salary_lookup" not in content, f"{file_path} todavía referencia 'salary_lookup'"


def test_python_modules_in_commands_and_agents():
    """Todos los módulos ejecutados con `python -m <module>` en commands/agents deben ser importables."""
    md_files = get_markdown_files()
    pattern = re.compile(r"python3?\s+-m\s+([a-zA-Z0-9_.]+)")

    found_modules = set()
    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8")
        matches = pattern.findall(content)
        for mod in matches:
            found_modules.add((mod, md_file.name))

    assert found_modules, "Se esperaba encontrar al menos un módulo python -m"

    for mod, filename in found_modules:
        if mod == "pytest":
            continue
        try:
            importlib.import_module(mod)
        except Exception as exc:
            pytest.fail(f"En {filename}: No se pudo importar '{mod}': {exc}")


def test_backtick_paths_in_commands_and_agents():
    """Rutas relativas referenciadas entre comillas invertidas que apuntan al repo deben existir."""
    md_files = get_markdown_files()
    # Busca expresiones entre backticks que parezcan rutas del repo (ej: backend/..., templates/..., .claude/...)
    path_pattern = re.compile(r"`([a-zA-Z0-9_.\-]+/[a-zA-Z0-9_./\-*<>]+)`")

    ignored_prefixes = (
        "http://", "https://", "cv/", "cover_letters/", "upskill/",
        "<portal", "<id", "<company", "<name", "<cv",
        "data/", "backend/profile.json", "backend/cv/", "backend/sessions", "backend/inbox",
        "backend/scraper/sources/", "n8n-local/", "memory/",
    )

    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8")
        for match in path_pattern.findall(content):
            # Limpiar posibles comodines o variables
            clean_path = match.split()[0].rstrip(";,:)")
            if any(clean_path.startswith(p) for p in ignored_prefixes):
                continue
            if clean_path.startswith("JH_HOME") or clean_path.startswith("POST") or clean_path.startswith("GET"):
                continue
            if "<" in clean_path or ">" in clean_path or "$" in clean_path:
                continue

            # Verificar existencia en el workspace
            target = REPO_ROOT / clean_path
            # Si contiene comodines '*', comprobar glob
            if "*" in clean_path:
                matching = list(REPO_ROOT.glob(clean_path))
                assert matching, f"En {md_file.name}: Ruta comodín no encontrada: '{clean_path}'"
            else:
                assert target.exists(), f"En {md_file.name}: Ruta no encontrada: '{clean_path}' ({target})"
