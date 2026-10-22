"""
profile_store.py — Lectura tolerante y escritura atómica de `profile.json`.

La ruta se lee de `config.PROFILE_PATH` en cada llamada (no se importa por valor) para que los tests y
`JH_PROFILE_PATH` puedan cambiarla. Un perfil ausente o corrupto equivale a `{}`: la app funciona sin él.
"""
import json
import os
import threading
from pathlib import Path

import config

_LOCK = threading.RLock()  # serializa leer-fusionar-escribir (PATCH) frente a otras escrituras del perfil


def load_profile() -> dict:
    """Perfil del usuario; `{}` si falta, es ilegible o no es un objeto JSON."""
    try:
        data = json.loads(Path(config.PROFILE_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def profile_exists() -> bool:
    return Path(config.PROFILE_PATH).is_file()


def save_profile(data: dict) -> Path:
    """Escribe el perfil de forma atómica (tmp + os.replace) e invalida la caché de idiomas del language_gate."""
    path = Path(config.PROFILE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with _LOCK:
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)
    from automation import language_gate  # import tardío: evita ciclos al importar el paquete

    language_gate.candidate_languages.cache_clear()
    return path


def update_profile(changes: dict, normalize=lambda p: p) -> dict:
    """Fusiona `changes` (claves de primer nivel) con el perfil guardado y lo escribe; devuelve el resultado.
    Leer, fusionar y escribir ocurren bajo un cerrojo: dos secciones que guardan a la vez no se pisan."""
    with _LOCK:
        merged = normalize({**load_profile(), **changes})
        save_profile(merged)
        return load_profile()


def modify_profile(change, normalize=lambda p: p) -> dict:
    """Aplica `change(perfil) -> perfil` bajo el mismo cerrojo que `update_profile` (leer, modificar, escribir
    sin pisarse con otras secciones que guardan a la vez) y devuelve el perfil guardado."""
    with _LOCK:
        modified = normalize(change(load_profile()))
        save_profile(modified)
        return load_profile()
