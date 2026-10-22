"""
ollama_status.py — ¿Hay Ollama en este equipo?

La app de escritorio no incluye Ollama (es un servicio grande y con su propio instalador). El asistente
lo consulta para decidir si ofrece instalarlo o elegir otro proveedor de IA. Nunca lanza: sin red o sin
Ollama el resultado es simplemente «no está en marcha».
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import requests
from pydantic import BaseModel

DEFAULT_BASE_URL = "http://127.0.0.1:11434"  # el mismo que usa el proveedor ollama (ai/http_providers.py)
INSTALL_URL = "https://ollama.com/download"
TIMEOUT_SECONDS = 2.0
MAX_MODELS = 50


class OllamaStatus(BaseModel):
    installed: bool
    running: bool
    models: list[str]
    install_url: str


def _known_locations() -> list[Path]:
    paths = [Path("/usr/local/bin/ollama"), Path("/usr/bin/ollama"), Path("/opt/homebrew/bin/ollama"),
             Path("/Applications/Ollama.app")]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        paths.append(Path(local) / "Programs" / "Ollama" / "ollama.exe")
    return paths


def _installed() -> bool:
    return shutil.which("ollama") is not None or any(p.exists() for p in _known_locations())


def _models(base_url: str, http_get) -> list[str] | None:
    """Nombres de los modelos descargados, o None si Ollama no responde."""
    try:
        res = http_get(f"{base_url.rstrip('/')}/api/tags", timeout=TIMEOUT_SECONDS)
        res.raise_for_status()
        entries = res.json().get("models", [])
        return [str(m["name"]) for m in entries if isinstance(m, dict) and m.get("name")][:MAX_MODELS]
    except (requests.RequestException, ValueError, AttributeError, TypeError):
        return None


def ollama_status(base_url: str | None = None, http_get=requests.get) -> OllamaStatus:
    models = _models(base_url or DEFAULT_BASE_URL, http_get)
    running = models is not None
    return OllamaStatus(installed=running or _installed(), running=running, models=models or [],
                        install_url=INSTALL_URL)
