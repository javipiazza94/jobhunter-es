# -*- mode: python ; coding: utf-8 -*-
"""Congela el backend para la app de escritorio (carpeta `jobhunter-api/`, modo onedir).

Uso: `python desktop/scripts/freeze_backend.py` (o `pyinstaller backend/desktop_freeze.spec`).

Los datos de serie se colocan con la misma disposición relativa que espera `config.py` cuando está
congelado (REPO_ROOT == BASE_DIR): `defaults/`, `templates/`, `templates/latex/`, `seeds/` y
`backend/profile.example.json`.
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

BACKEND = Path(SPECPATH)
ROOT = BACKEND.parent

datas = [
    (str(BACKEND / "defaults"), "defaults"),
    (str(BACKEND / "templates"), "templates"),
    (str(ROOT / "templates" / "latex"), "templates/latex"),
    (str(ROOT / "seeds"), "seeds"),
    (str(BACKEND / "profile.example.json"), "backend"),
]
# El driver de Playwright (node + cli) va en el paquete; los navegadores NO (se descargan bajo demanda).
datas += collect_data_files("playwright")
datas += collect_data_files("docx")
datas += copy_metadata("keyring")

# Se importan por nombre en tiempo de ejecución (importlib, registro de scrapers, workers de uvicorn).
hiddenimports = []
for package in ("scraper", "automation", "ai", "uvicorn", "keyring.backends"):
    hiddenimports += collect_submodules(package)
hiddenimports += [
    "main", "job_manager", "inbox_job", "inbox_watcher", "ollama_status", "secrets_store", "profile_store",
]

a = Analysis(
    [str(BACKEND / "desktop_main.py")],
    pathex=[str(BACKEND)],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "ruff"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="jobhunter-api",
    console=True,  # la app lee el puerto de stdout; en Windows la ventana se oculta al lanzarlo
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="jobhunter-api", upx=False)
