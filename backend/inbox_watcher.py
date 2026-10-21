"""
inbox_watcher.py — Carga sola en la BD lo que se deja en JH_HOME/inbox/ (a mano, n8n o un agente externo).

Algunos agentes (p. ej. Cowork) no tienen shell ni alcanzan la API: su único canal son ficheros. Mientras la API está encendida,
este vigilante los recoge, así que no hace falta ejecutar ningún cargador a mano:
- `candidaturas_*.txt` → scripts/load_inbox_applications.py --save
- `ofertas_*.txt`      → scripts/load_inbox_offers.py --save
Antes de guardar hace una copia de la BD (se conservan las últimas). Los cargadores deduplican, nunca bajan
un estado y dejan en el fichero las filas dudosas; el vigilante no reprocesa un fichero hasta que cambia.
Nunca envía nada: solo escribe en la BD.
"""
import logging
import re
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from inbox_job import BACKUP_PREFIX, backup_dir

BACKEND_DIR = Path(__file__).parent
LOADERS = (
    ("candidaturas_*.txt", BACKEND_DIR / "scripts" / "load_inbox_applications.py"),
    ("ofertas_*.txt", BACKEND_DIR / "scripts" / "load_inbox_offers.py"),
)
LOADER_TIMEOUT_SECONDS = 600
OUTPUT_LINES = 40

_SECTION = re.compile(r"^== ([\w ]+): (\d+)", re.M)
_OFFERS_SAVED = re.compile(r"guardadas=(\d+)")
_KEYS = {"nuevas": "new", "actualizadas": "updated", "dudosas": "doubtful",
         "invalidas": "invalid", "Por revisar": "to_review"}

log = logging.getLogger("inbox_watcher")


def _count_rows(path: Path) -> int:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    return sum(1 for line in lines if line.strip() and not line.lstrip().startswith("#"))


class InboxWatcher:
    def __init__(self, inbox_dir: Path, db_path: Path, runner=subprocess.run, interval: float = 60,
                 settle_seconds: float = 5, keep: int = 10, now=datetime.now, clock=time.time):
        self.inbox_dir, self.db_path, self.runner = Path(inbox_dir), Path(db_path), runner
        self.interval, self.settle, self.keep, self._now, self._clock = interval, settle_seconds, keep, now, clock
        self._seen: dict[str, tuple[int, int]] = {}  # fichero → (mtime_ns, tamaño) ya procesado
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last: dict | None = None
        self._changes = 0

    # ── ficheros ───────────────────────────────────────────────────────────────
    def _files(self) -> list[tuple[Path, Path]]:
        """(fichero, cargador) de todo lo que hay en el inbox."""
        found = []
        for pattern, loader in LOADERS:
            found += [(f, loader) for f in sorted(self.inbox_dir.glob(pattern)) if f.is_file()]
        return found

    @staticmethod
    def _fingerprint(f: Path) -> tuple[int, int]:
        st = f.stat()
        return st.st_mtime_ns, st.st_size

    def _ready(self, f: Path, force: bool) -> bool:
        if force:
            return True
        if self.settle > 0 and self._clock() - f.stat().st_mtime < self.settle:
            return False  # aún se está escribiendo
        return self._seen.get(f.name) != self._fingerprint(f)

    # ── copia de seguridad ─────────────────────────────────────────────────────
    def _backup(self) -> None:
        backup_dir(self.db_path).mkdir(parents=True, exist_ok=True)
        dest = backup_dir(self.db_path) / f"{BACKUP_PREFIX}{self._now():%Y%m%d-%H%M%S}"
        src, dst = sqlite3.connect(str(self.db_path)), sqlite3.connect(str(dest))
        try:
            src.backup(dst)  # seguro con la BD en uso (WAL), a diferencia de copiar el fichero
        finally:
            dst.close()
            src.close()
        for old in sorted(backup_dir(self.db_path).glob(BACKUP_PREFIX + "*"))[:-self.keep]:
            old.unlink()

    # ── ejecución ──────────────────────────────────────────────────────────────
    def run_once(self, force: bool = False) -> dict | None:
        """Procesa lo que haya nuevo. Devuelve el informe, o None si no había nada que hacer."""
        if not self._lock.acquire(blocking=force):
            return None
        try:
            todo = [(f, loader) for f, loader in self._files() if self._ready(f, force)]
            if not todo:
                return None
            informe = {"at": self._now().isoformat(timespec="seconds"), "files": [f.name for f, _ in todo],
                       "new": 0, "updated": 0, "doubtful": 0, "invalid": 0, "to_review": 0,
                       "error": False, "output": ""}
            salida: list[str] = []
            try:
                self._backup()
                for loader in dict.fromkeys(loader for _, loader in todo):
                    files = [str(f) for f, ld in todo if ld == loader]
                    done = self.runner([sys.executable, str(loader), *files, "--save"], cwd=BACKEND_DIR,
                                       capture_output=True, text=True, timeout=LOADER_TIMEOUT_SECONDS)
                    out = (done.stdout or "") + (done.stderr or "")
                    salida.append(out)
                    self._add_counts(informe, out)
                    if done.returncode != 0:
                        informe["error"] = True
            except Exception as exc:  # noqa: BLE001 — el vigilante nunca debe tumbar la API
                log.exception("Fallo cargando el inbox")
                informe["error"] = True
                salida.append(f"{type(exc).__name__}: {exc}")
            informe["output"] = "\n".join("\n".join(salida).strip().splitlines()[-OUTPUT_LINES:])
            self._remember(todo)
            if informe["new"] + informe["updated"] > 0:
                self._changes += 1
            self._last = informe
            return informe
        finally:
            self._lock.release()

    @staticmethod
    def _add_counts(informe: dict, out: str) -> None:
        for name, n in _SECTION.findall(out):
            if name in _KEYS:
                informe[_KEYS[name]] += int(n)
        for n in _OFFERS_SAVED.findall(out):
            informe["new"] += int(n)

    def _remember(self, processed: list[tuple[Path, Path]]) -> None:
        """Apunta los ficheros que el cargador ha conservado; los borrados se olvidan."""
        for f, _ in processed:
            if f.exists():
                self._seen[f.name] = self._fingerprint(f)
            else:
                self._seen.pop(f.name, None)

    # ── estado para la API ─────────────────────────────────────────────────────
    def status(self) -> dict:
        return {
            "pending": [{"name": f.name, "rows": _count_rows(f)} for f, _ in self._files()],
            "last": self._last,
            "changes": self._changes,
            "automatic": self._thread is not None and self._thread.is_alive(),
        }

    # ── hilo de fondo ──────────────────────────────────────────────────────────
    def start(self) -> None:
        if self.interval <= 0 or (self._thread and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="inbox-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception:  # noqa: BLE001
                log.exception("Fallo en el vigilante del inbox")
            self._stop.wait(self.interval)
