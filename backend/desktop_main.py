"""
desktop_main.py — Punto de entrada del backend dentro de la app de escritorio (Tauri + PyInstaller).

La app lo lanza como proceso hijo y espera una línea `JH_READY port=N` por stdout. Diferencias con
`uvicorn main:app`:

- El puerto lo abre este proceso (puerto 0 en 127.0.0.1) y se entrega ya abierto a uvicorn: no hay
  carrera entre «buscar un puerto libre» y «ocuparlo».
- Los datos de usuario van a la carpeta de datos del sistema (`platformdirs`) salvo que haya JH_HOME.
- CORS solo admite los orígenes del webview de Tauri; `Host` sigue siendo localhost/127.0.0.1 (el puerto
  no cuenta al compararlo). La cabecera `X-JH-Client` sigue siendo obligatoria. Ver
  docs/adr/0002-api-local-en-app-de-escritorio.md.
- Si la app muere, el cierre de stdin para el servidor (solo con `JH_PARENT_WATCH=1`).
- `-m <módulo> [args]` se comporta como `python -m`: `job_manager` lanza los scrapers con
  `sys.executable -m scraper.jobs`, y congelado `sys.executable` es este mismo programa.
"""
from __future__ import annotations

import os
import runpy
import socket
import sys
import threading
from collections.abc import Callable, MutableMapping
from pathlib import Path

APP_NAME = "jobhunter"
# Orígenes con los que el webview de Tauri 2 sirve la página: tauri://localhost (Linux, macOS) y
# http(s)://tauri.localhost (Windows, según useHttpsScheme).
TAURI_ORIGINS = ("tauri://localhost", "http://tauri.localhost", "https://tauri.localhost")
ALLOWED_HOSTS = "localhost,127.0.0.1"
READY_PREFIX = "JH_READY port="
# Si uvicorn no cierra a tiempo tras el EOF de stdin, se sale a la fuerza: un huérfano no puede quedar vivo.
FORCE_EXIT_AFTER_SECONDS = 10.0


def default_home() -> Path:
    """Carpeta de datos del sistema: ~/.local/share/jobhunter, %APPDATA%\\jobhunter o
    ~/Library/Application Support/jobhunter."""
    from platformdirs import user_data_dir

    return Path(user_data_dir(APP_NAME, appauthor=False, roaming=True))


def prepare_environment(env: MutableMapping[str, str]) -> None:
    """Fija el entorno de escritorio. Debe ejecutarse antes de importar `config`, que lo lee al importarse.

    JH_HOME y PLAYWRIGHT_BROWSERS_PATH respetan lo que ya haya definido el usuario. CORS y hosts de
    confianza **no**: en escritorio son los de Tauri (más `JH_DESKTOP_EXTRA_ORIGINS`, para `tauri dev`).
    """
    if not env.get("JH_HOME"):
        env["JH_HOME"] = str(default_home())
    env.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(Path(env["JH_HOME"]) / "browsers"))
    extra = [o.strip() for o in env.get("JH_DESKTOP_EXTRA_ORIGINS", "").split(",") if o.strip()]
    env["CORS_ORIGINS"] = ",".join([*TAURI_ORIGINS, *extra])
    env["ALLOWED_HOSTS"] = ALLOWED_HOSTS
    env["JH_DESKTOP"] = "1"
    bundled = env.get("JH_BUNDLED_BIN")
    if bundled:
        env["PATH"] = bundled + os.pathsep + env.get("PATH", "")


def open_listener(host: str = "127.0.0.1") -> socket.socket:
    """Socket de escucha en loopback con un puerto libre asignado por el sistema."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, 0))
        sock.listen(128)
    except OSError:
        sock.close()
        raise
    return sock


def announce_ready(port: int, out=None) -> None:
    """Línea que la app lee de stdout para saber en qué puerto está la API."""
    print(f"{READY_PREFIX}{port}", file=out or sys.stdout, flush=True)


def watch_stdin(stream, on_eof: Callable[[], None]) -> threading.Thread:
    """Llama a `on_eof` cuando `stream` se cierra (la app que nos lanzó ha terminado)."""

    def _run() -> None:
        try:
            while stream.read(4096):
                pass
        except (OSError, ValueError):
            pass
        on_eof()

    thread = threading.Thread(target=_run, name="jh-stdin-watch", daemon=True)
    thread.start()
    return thread


def run_module(module: str, args: list[str]) -> int:
    """Equivale a `python -m <module> <args>`."""
    sys.argv = [module, *args]
    runpy.run_module(module, run_name="__main__", alter_sys=True)
    return 0


def serve() -> int:
    import uvicorn

    from main import app  # tras prepare_environment: config lee el entorno al importarse

    sock = open_listener()
    port = sock.getsockname()[1]

    class _Server(uvicorn.Server):
        async def startup(self, sockets=None):
            await super().startup(sockets=sockets)
            if self.started:
                announce_ready(port)

    server = _Server(uvicorn.Config(app, log_level="info"))

    if os.environ.get("JH_PARENT_WATCH") == "1" and sys.stdin is not None:
        def _stop() -> None:
            server.should_exit = True
            timer = threading.Timer(FORCE_EXIT_AFTER_SECONDS, os._exit, args=(0,))
            timer.daemon = True
            timer.start()

        watch_stdin(sys.stdin.buffer, _stop)

    try:
        server.run(sockets=[sock])
    finally:
        sock.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    import multiprocessing

    multiprocessing.freeze_support()
    args = list(sys.argv[1:] if argv is None else argv)
    prepare_environment(os.environ)
    if args[:1] == ["-m"] and len(args) >= 2:
        return run_module(args[1], args[2:])
    return serve()


if __name__ == "__main__":
    sys.exit(main())
