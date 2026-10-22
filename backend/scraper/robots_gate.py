"""scraper/robots_gate.py — Comprobación de robots.txt antes de lanzar fuentes HTML/Playwright."""
from __future__ import annotations

import logging
from automation import robots_check

logger = logging.getLogger(__name__)


class RobotsRefused(Exception):
    """robots.txt no permite acceder a la URL de inicio de la fuente."""


def check_robots(start_url: str | None, source_id: str | None = None, is_acknowledged: bool = False) -> bool:
    """Comprueba si robots.txt permite acceder a `start_url`.

    Lanza `RobotsRefused` si no está permitido.
    LinkedIn queda exenta únicamente si está confirmada/aceptada (`is_acknowledged=True`).
    """
    if not start_url:
        return True
    if source_id == "linkedin" and is_acknowledged:
        return True
    code, msg = robots_check.gate(start_url)
    if code != 0:
        raise RobotsRefused(f"robots.txt no permite {start_url} ({msg})")
    return True
