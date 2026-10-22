"""
secrets_store.py — Claves de API y contraseña SMTP en el llavero del sistema (`keyring`).

Lectura: variable de entorno primero (modo desarrollador / instalaciones existentes), luego el llavero.
Nunca se registra ni se devuelve el valor de un secreto; los errores del llavero solo citan el tipo de fallo.
Si el llavero no está disponible (p. ej. Linux sin Secret Service), `get_secret` devuelve `None` y la app
sigue funcionando con variables de entorno; `set_secret`/`delete_secret` lanzan `SecretStoreUnavailable`.
"""
import logging
import os

try:
    import keyring
    from keyring.errors import PasswordDeleteError
except ImportError:  # build sin keyring: la app sigue funcionando con variables de entorno
    keyring = None

    class PasswordDeleteError(Exception):
        pass

log = logging.getLogger(__name__)

SERVICE = "jobhunter"
ENV_FALLBACK = {
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "openai_api_key": "OPENAI_API_KEY",
    "smtp_password": "GMAIL_APP_PASSWORD",
}


class SecretStoreUnavailable(Exception):
    """El llavero del sistema no está disponible o ha fallado."""


def _check(name: str) -> None:
    if name not in ENV_FALLBACK:
        raise ValueError(f"Secreto desconocido: {name!r}")


def get_secret(name: str) -> str | None:
    """Valor del secreto: variable de entorno si existe, si no el llavero; `None` si no hay o falla."""
    _check(name)
    env = os.environ.get(ENV_FALLBACK[name])
    if env:
        return env
    if keyring is None:
        return None
    try:
        return keyring.get_password(SERVICE, name) or None
    except Exception as exc:  # noqa: BLE001 — cualquier fallo del backend equivale a «sin secreto»
        log.debug("Llavero no disponible al leer %s: %s", name, type(exc).__name__)
        return None


def set_secret(name: str, value: str) -> None:
    """Guarda el secreto en el llavero."""
    _check(name)
    if not isinstance(value, str) or not value:
        raise ValueError("El secreto debe ser un texto no vacío")
    if keyring is None:
        raise SecretStoreUnavailable("El llavero del sistema no está instalado. Usa la variable de entorno correspondiente.")
    try:
        keyring.set_password(SERVICE, name, value)
    except Exception as exc:  # noqa: BLE001
        raise SecretStoreUnavailable(
            f"No se pudo guardar en el llavero del sistema ({type(exc).__name__}). "
            "Usa la variable de entorno correspondiente."
        ) from None


def delete_secret(name: str) -> None:
    """Borra el secreto del llavero; si no existía no hace nada."""
    _check(name)
    if keyring is None:
        raise SecretStoreUnavailable("El llavero del sistema no está instalado.")
    try:
        keyring.delete_password(SERVICE, name)
    except PasswordDeleteError:
        return
    except Exception as exc:  # noqa: BLE001
        raise SecretStoreUnavailable(
            f"No se pudo borrar del llavero del sistema ({type(exc).__name__})."
        ) from None


def has_secret(name: str) -> bool:
    """¿Hay un valor disponible (entorno o llavero)?"""
    return get_secret(name) is not None
