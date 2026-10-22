"""
browser_install.py — Descarga el Chromium de Playwright la primera vez que se usa un navegador.

El instalador de la app de escritorio no incluye Chromium (cientos de MB que solo hacen falta para
rellenar formularios y para algunos portales). Antes de lanzarlo, `ensure_chromium()` comprueba si la
versión que pide la librería de Playwright instalada ya está en `PLAYWRIGHT_BROWSERS_PATH` y, si no, la
descarga con el propio driver (`playwright install chromium`). Si hay un Chromium del sistema se usa ese
y no se descarga nada.
"""
from __future__ import annotations

import asyncio
import logging
import re
import shutil
import subprocess
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

INSTALL_TIMEOUT_SECONDS = 1200
_MARKER = "INSTALLATION_COMPLETE"  # lo escribe Playwright al terminar de descomprimir
_LOCATION = re.compile(r"Install location:\s*(.+)")
_lock = threading.Lock()


class BrowserInstallError(RuntimeError):
    """No se pudo preparar Chromium (sin red, sin espacio, driver ausente…). El mensaje es legible."""


def system_chromium() -> str | None:
    return shutil.which("chromium") or shutil.which("chromium-browser")


def _driver() -> tuple[str, list[str], dict[str, str]]:
    from playwright._impl._driver import compute_driver_executable, get_driver_env

    node, cli = compute_driver_executable()
    return str(node), [str(cli)], dict(get_driver_env())


def _run_driver(*args: str, timeout: float) -> subprocess.CompletedProcess:
    try:
        node, cli, env = _driver()
    except Exception as exc:  # librería ausente o driver no empaquetado
        raise BrowserInstallError(f"No se encuentra el instalador de navegadores de Playwright: {exc}") from exc
    return subprocess.run([node, *cli, *args], env=env, capture_output=True, text=True, timeout=timeout)


def _required_dirs() -> list[Path]:
    """Carpetas de Chromium que esta versión de Playwright necesita (no cuenta FFmpeg: solo sirve para vídeo)."""
    res = _run_driver("install", "--dry-run", "chromium", timeout=60)
    if res.returncode != 0:
        raise BrowserInstallError(f"No se pudo consultar qué Chromium necesita Playwright: {res.stderr.strip()[-300:]}")
    dirs = [Path(m.group(1).strip()) for m in _LOCATION.finditer(res.stdout)]
    return [d for d in dirs if d.name.startswith("chromium")]


def chromium_installed() -> bool:
    dirs = _required_dirs()
    return bool(dirs) and all((d / _MARKER).exists() for d in dirs)


def ensure_chromium() -> None:
    """Deja Chromium listo para `playwright.chromium.launch()`. Idempotente y seguro entre hilos."""
    if system_chromium():
        return
    with _lock:
        if chromium_installed():
            return
        logger.info("Descargando Chromium de Playwright (solo la primera vez)…")
        try:
            res = _run_driver("install", "chromium", timeout=INSTALL_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as exc:
            raise BrowserInstallError("La descarga de Chromium tardó demasiado. Comprueba la conexión y reinténtalo.") from exc
        if res.returncode != 0:
            detail = (res.stderr or res.stdout).strip()[-300:]
            raise BrowserInstallError(
                "No se pudo descargar Chromium (¿sin conexión o sin espacio en disco?). "
                f"Reinténtalo con conexión a internet. Detalle: {detail}")
        if not chromium_installed():
            raise BrowserInstallError("Chromium se descargó pero Playwright no lo encuentra. Reinténtalo.")


async def ensure_chromium_async() -> None:
    """Igual que `ensure_chromium()` sin bloquear el bucle de eventos (la descarga puede tardar minutos)."""
    await asyncio.to_thread(ensure_chromium)
