"""
job_manager.py — Lanza trabajos pesados (scrapers) en un proceso aparte y lleva su estado.

Cada trabajo es un subproceso (`python -m scraper.jobs <fuente>`) con su log, un tiempo límite y un
estado visible (running / succeeded / failed / timeout). Combina el RunGate (no dos a la vez de la
misma fuente, espera entre ejecuciones) con el registro de los últimos trabajos. El estado vive en
el proceso de la API: se pierde al reiniciarla (un subproceso en marcha seguiría su curso).
"""
import itertools
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from config import LOGS_DIR
from rate_gate import RunGate

BACKEND_DIR = Path(__file__).parent


def default_launcher(source: str, log_file) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "scraper.jobs", source],
        cwd=BACKEND_DIR, stdout=log_file, stderr=subprocess.STDOUT, start_new_session=True,
    )


@dataclass
class Job:
    id: str
    source: str
    status: str = "running"          # running | succeeded | failed | timeout
    started_at: str = ""
    finished_at: str | None = None
    returncode: int | None = None
    log_path: str = ""
    done: threading.Event = field(default_factory=threading.Event, repr=False)

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in ("id", "source", "status", "started_at", "finished_at", "returncode")}


class JobManager:
    def __init__(self, gate: RunGate, launcher=default_launcher, log_dir: Path | None = None,
                 timeout: float = 1800, max_history: int = 50):
        self._gate = gate
        self._launcher = launcher
        self._log_dir = Path(log_dir) if log_dir else LOGS_DIR
        self._timeout = timeout
        self._max_history = max_history
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._seq = itertools.count(1)

    def start(self, source: str) -> Job:
        """Lanza el trabajo o lanza GateRejected (409 ya en marcha / 429 ejecutado hace poco)."""
        self._gate.acquire(source)
        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
            job = Job(id=f"{int(time.time())}-{next(self._seq)}", source=source,
                      started_at=datetime.now().isoformat(timespec="seconds"))
            job.log_path = str(self._log_dir / f"{job.id}-{source}.log")
            with open(job.log_path, "wb") as log:
                proc = self._launcher(source, log)
        except BaseException:
            self._gate.cancel(source)  # no llegó a arrancar: no hay que esperar para reintentar
            raise
        with self._lock:
            self._jobs[job.id] = job
            for old in list(self._jobs)[:-self._max_history]:
                del self._jobs[old]
        threading.Thread(target=self._watch, args=(job, proc), daemon=True).start()
        return job

    def _watch(self, job: Job, proc) -> None:
        try:
            try:
                rc = proc.wait(timeout=self._timeout)
                job.status = "succeeded" if rc == 0 else "failed"
            except subprocess.TimeoutExpired:
                proc.kill()
                rc = proc.wait()
                job.status = "timeout"
            job.returncode = rc
        except BaseException:
            job.status = "failed"
            raise
        finally:
            job.finished_at = datetime.now().isoformat(timespec="seconds")
            self._gate.release(job.source)
            job.done.set()

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        with self._lock:
            return list(reversed(self._jobs.values()))

    def tail(self, job: Job, lines: int = 40) -> str:
        try:
            return "".join(Path(job.log_path).read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)[-lines:])
        except OSError:
            return ""
