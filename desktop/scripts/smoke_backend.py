"""Prueba de humo del backend congelado (o de `backend/desktop_main.py` con --python).

Arranca el programa como lo hace la app (JH_HOME temporal, stdin abierto, JH_PARENT_WATCH=1), lee el
puerto de la línea `JH_READY`, comprueba que la API responde y que las protecciones de la ADR-0001/0002
siguen activas con un puerto dinámico y el origen de Tauri, que `-m scraper.jobs` funciona, y que el
proceso termina solo al cerrar stdin.

Uso: python desktop/scripts/smoke_backend.py <ruta al ejecutable jobhunter-api>
Sale con código 0 si todo pasa.
"""
from __future__ import annotations

import http.client
import json
import os
import queue
import sqlite3
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

READY = "JH_READY port="
TAURI = "tauri://localhost"
CLIENT = {"X-JH-Client": "dashboard"}


def request(port: int, method: str, path: str, headers: dict[str, str] | None = None, host: str | None = None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    hdrs = {"Host": host or f"127.0.0.1:{port}", **(headers or {})}
    conn.request(method, path, headers=hdrs)
    res = conn.getresponse()
    body = res.read().decode("utf-8", "replace")
    out = (res.status, {k.lower(): v for k, v in res.getheaders()}, body)
    conn.close()
    return out


def read_ready(proc: subprocess.Popen, timeout: float) -> int:
    lines: queue.Queue[str] = queue.Queue()

    def pump() -> None:
        for line in proc.stdout:  # type: ignore[union-attr]
            lines.put(line.rstrip())
            if line.startswith(READY):
                return

    threading.Thread(target=pump, daemon=True).start()
    seen = []
    while True:
        try:
            line = lines.get(timeout=timeout)
        except queue.Empty:
            raise SystemExit(f"El backend no anunció el puerto en {timeout:.0f} s. Salida: {seen[-5:]}")
        seen.append(line)
        if line.startswith(READY):
            return int(line.removeprefix(READY))


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    # El programa se lanza con cwd=<carpeta temporal>: una ruta relativa dejaría de resolverse.
    command = [str(Path(argv[1]).resolve()), *argv[2:]]
    failures: list[str] = []

    def check(name: str, ok: bool, detail: object = "") -> None:
        print(f"{'OK  ' if ok else 'FALLO'} {name}" + ("" if ok else f" -> {detail}"))
        if not ok:
            failures.append(name)

    home = Path(tempfile.mkdtemp(prefix="jh-smoke-"))
    env = {k: v for k, v in os.environ.items() if not k.startswith(("JH_", "CORS_", "ALLOWED_", "PLAYWRIGHT_"))}
    env.update(JH_HOME=str(home), JH_PARENT_WATCH="1", JH_INBOX_POLL_SECONDS="0", PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    proc = subprocess.Popen(command, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", cwd=home)
    try:
        port = read_ready(proc, 120)
        check("anuncia el puerto", port > 0, port)

        status, h, body = request(port, "GET", "/api/stats", {"Origin": TAURI})
        check("GET /api/stats con origen de Tauri", status == 200 and h.get("access-control-allow-origin") == TAURI, (status, h))
        check("datos de serie empaquetados (tracks)", request(port, "GET", "/api/tracks")[0] == 200)
        status, _, body = request(port, "GET", "/api/setup/markets")
        check("datos de serie empaquetados (mercados)", status == 200 and len(json.loads(body)) > 0, status)
        check("plantillas LaTeX empaquetadas", request(port, "GET", "/api/templates")[0] == 200)
        status, _, body = request(port, "GET", "/api/ai/ollama")
        check("detección de Ollama", status == 200 and "install_url" in body, status)
        check("el JH_HOME es el temporal", (home / "job_hunter.db").exists())

        check("Host ajeno -> 400", request(port, "GET", "/api/stats", host=f"evil.example:{port}")[0] == 400)
        check("Host de la LAN -> 400", request(port, "GET", "/api/stats", host=f"192.168.1.20:{port}")[0] == 400)
        _, h, _ = request(port, "GET", "/api/stats", {"Origin": "http://evil.example"})
        check("origen ajeno sin permiso CORS", "access-control-allow-origin" not in h, h)
        _, h, _ = request(port, "GET", "/api/stats", {"Origin": "http://localhost:3010"})
        check("el origen del dashboard web no tiene permiso en escritorio", "access-control-allow-origin" not in h, h)
        check("POST sin cabecera -> 403", request(port, "POST", "/api/scraper/run", {"Origin": TAURI})[0] == 403)
        status, h, _ = request(port, "OPTIONS", "/api/applications/x", {
            "Origin": TAURI, "Access-Control-Request-Method": "DELETE", "Access-Control-Request-Headers": "x-jh-client"})
        check("preflight desde Tauri", status == 200 and h.get("access-control-allow-origin") == TAURI, (status, h))
        status, _, _ = request(port, "POST", "/api/scraper/run?source=nope", {**CLIENT, "Origin": TAURI})
        check("POST con cabecera llega al handler (no 403)", status != 403, status)

        proc.stdin.close()  # type: ignore[union-attr]
        try:
            code = proc.wait(timeout=30)
            check("se para solo al cerrar stdin", code == 0, code)
        except subprocess.TimeoutExpired:
            check("se para solo al cerrar stdin", False, "sigue vivo tras 30 s")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()

    # Subproceso `-m` (como lo lanza job_manager): carga las semillas en la BD del JH_HOME.
    res = subprocess.run([*command, "-m", "scraper.jobs", "seed"], env=env, cwd=home, capture_output=True,
                         text=True, encoding="utf-8", errors="replace", timeout=180)
    check("-m scraper.jobs seed termina bien", res.returncode == 0, (res.returncode, res.stdout[-300:], res.stderr[-300:]))
    try:
        n = sqlite3.connect(home / "job_hunter.db").execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    except sqlite3.Error as exc:
        n = exc
    check("las semillas están en la BD", isinstance(n, int) and n > 0, n)

    # El driver de Playwright viaja en el paquete (Chromium no: se descarga bajo demanda).
    res = subprocess.run([*command, "-m", "automation.browser_install"], env={**env, "PLAYWRIGHT_BROWSERS_PATH": str(home / "nav")},
                         cwd=home, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    check("el driver de Playwright responde", res.returncode == 0 and "chromium no instalado" in res.stdout,
          (res.returncode, res.stdout[-200:], res.stderr[-300:]))

    print("\nTODO CORRECTO" if not failures else f"\nFALLARON {len(failures)}: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
