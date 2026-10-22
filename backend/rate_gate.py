"""
rate_gate.py — Límite de uso en memoria para las tareas que la API lanza en segundo plano.

Una fuente no puede ejecutarse dos veces a la vez (409) ni repetirse antes de `cooldown_seconds`
desde que terminó la anterior (429 + Retry-After). Protege a los portales de scraping de
peticiones repetidas desde tu IP (bloqueos) y evita apilar procesos de Playwright.
Un trabajo que recorre varios portales (el pipeline de un track) reserva también esos portales (`also`): mientras
corre, ni otro track ni la fuente suelta pueden usarlos (409), así no se abren dos Chromium/sesiones de LinkedIn a la
vez. Para esas fuentes compartidas solo cuenta el solapamiento, no la espera; al terminar sí empieza su espera para
las ejecuciones sueltas.
El estado vive en el proceso: se reinicia con él (p. ej. al recargar uvicorn --reload).
"""
import math
import threading
import time
from collections.abc import Iterable


class GateRejected(Exception):
    def __init__(self, status: int, detail: str, retry_after: int | None = None):
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.retry_after = retry_after


class RunGate:
    def __init__(self, cooldown_seconds: float, clock=time.monotonic, overrides: dict[str, float] | None = None):
        self._cooldown = cooldown_seconds
        self._overrides = overrides or {}  # espera propia de algunas fuentes (p. ej. 0 para las locales)
        self._clock = clock
        self._lock = threading.Lock()
        self._running: set[str] = set()
        self._finished_at: dict[str, float] = {}

    def acquire(self, key: str, also: Iterable[str] = ()) -> None:
        """Reserva el turno de `key` (y las fuentes compartidas `also`, todo o nada) o lanza GateRejected."""
        also = tuple(also)
        with self._lock:
            if key in self._running:
                raise GateRejected(409, f"«{key}» ya se está ejecutando; espera a que termine.")
            busy = next((k for k in also if k in self._running), None)
            if busy is not None:
                raise GateRejected(409, f"«{busy}» está en uso por otra búsqueda; espera a que termine.")
            finished = self._finished_at.get(key)
            cooldown = self._overrides.get(key, self._cooldown)
            if finished is not None and cooldown > 0:
                remaining = cooldown - (self._clock() - finished)
                if remaining > 0:
                    wait = math.ceil(remaining)
                    raise GateRejected(
                        429, f"«{key}» se ejecutó hace poco; vuelve a intentarlo en {wait} s.", retry_after=wait
                    )
            self._running.add(key)
            self._running.update(also)

    def release(self, key: str, also: Iterable[str] = ()) -> None:
        """Libera el turno (y las fuentes compartidas) y empieza a contar la espera desde ahora."""
        with self._lock:
            now = self._clock()
            for k in (key, *also):
                self._running.discard(k)
                self._finished_at[k] = now

    def cancel(self, key: str, also: Iterable[str] = ()) -> None:
        """Libera el turno SIN empezar la espera: la ejecución ni siquiera llegó a arrancar."""
        with self._lock:
            for k in (key, *also):
                self._running.discard(k)

