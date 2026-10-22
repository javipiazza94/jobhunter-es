"""Test para validar que los comandos, agentes y skills de Claude Code (.claude/commands, .claude/agents y
.claude/skills) apuntan a rutas existentes y a CLIs que funcionan (`python -m <mod> --help` termina con 0) y no
referencian artefactos obsoletos (perfil en Markdown, tracker CSV, informes fuera de JH_HOME/reports).
"""

from __future__ import annotations

import importlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLAUDE_DIR = REPO_ROOT / ".claude"
COMMANDS_DIR = CLAUDE_DIR / "commands"
AGENTS_DIR = CLAUDE_DIR / "agents"
SKILLS_DIR = CLAUDE_DIR / "skills"
BACKEND_DIR = REPO_ROOT / "backend"

# Artefactos de la versión original (ai-job-search) que en este repo no existen o se sustituyeron.
OBSOLETE = {
    "seen_jobs.json": "la deduplicación vive en la BD (job_key)",
    "salary_lookup": "no se porta",
    "01-candidate-profile.md": "el perfil es JH_HOME/profile.json (profile_store)",
    "job_search_tracker.csv": "las candidaturas viven en JH_HOME/job_hunter.db",
    "report-YYYY": "los informes de upskill van a JH_HOME/reports/upskill-<fecha>.md",
}


def get_markdown_files() -> list[Path]:
    files = (list(COMMANDS_DIR.glob("*.md")) + list(AGENTS_DIR.glob("*.md"))
             + sorted(SKILLS_DIR.rglob("*.md")))
    assert files, "No se encontraron archivos markdown en .claude/commands, .claude/agents o .claude/skills"
    assert any(f.is_relative_to(SKILLS_DIR) for f in files), "Se esperaban skills en .claude/skills"
    return files


def test_no_obsolete_artifacts_in_claude():
    """Ningún comando, agente ni skill referencia artefactos obsoletos (ver OBSOLETE)."""
    all_files = list(CLAUDE_DIR.rglob("*.md"))
    assert all_files
    for file_path in all_files:
        content = file_path.read_text(encoding="utf-8")
        for term, why in OBSOLETE.items():
            assert term not in content, f"{file_path} todavía referencia '{term}' ({why})"
    assert not (SKILLS_DIR / "job-application-assistant" / "01-candidate-profile.md").exists()


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


def test_python_m_clis_run_help():
    """Cada `python -m <mod>` (salvo pytest) es un CLI de verdad: `--help` termina con código 0."""
    pattern = re.compile(r"python3?\s+-m\s+([a-zA-Z0-9_.]+)")
    modules = sorted({m for f in get_markdown_files() for m in pattern.findall(f.read_text(encoding="utf-8"))} - {"pytest"})
    assert modules
    for mod in modules:
        proc = subprocess.run([sys.executable, "-m", mod, "--help"], cwd=BACKEND_DIR, capture_output=True,
                              text=True, timeout=60)
        assert proc.returncode == 0, f"`python -m {mod} --help` falló: {proc.stderr[-500:]}"


def test_subcommands_and_flags_used_exist():
    """Los subcomandos y opciones `--x` que usan los .md tras `python -m <mod>` aparecen en su `--help`."""
    line_re = re.compile(r"python3?\s+-m\s+([a-zA-Z0-9_.]+)([^\n`]*)")
    for md_file in get_markdown_files():
        for mod, rest in line_re.findall(md_file.read_text(encoding="utf-8")):
            if mod == "pytest":
                continue
            help_text = _help(mod)
            words = rest.split()
            choices = re.search(r"\{([a-z,\-]+)\}", help_text)
            if choices and words and re.fullmatch(r"[a-z][a-z-]+", words[0]):
                if words[0] not in choices.group(1).split(","):
                    pytest.fail(f"En {md_file.name}: `{mod}` no tiene el subcomando '{words[0]}'")
                help_text = _help(mod, words[0])
            for flag in re.findall(r"(?<![\w-])(--[a-z][a-z0-9-]*)", rest):
                assert flag in help_text, f"En {md_file.name}: `{mod}` no tiene la opción {flag}"


def _help(*args: str) -> str:
    return subprocess.run([sys.executable, "-m", *args, "--help"], cwd=BACKEND_DIR, capture_output=True,
                          text=True, timeout=60).stdout


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
