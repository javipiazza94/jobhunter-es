"""
base.py — Interfaz común de los proveedores de IA, errores y utilidades de JSON.

`generate_json` es común: incrusta el esquema en el prompt, extrae el primer objeto JSON de la
respuesta (con o sin vallas ```json) y valida las claves `required` de primer nivel.
Nunca se incluyen claves de API en los mensajes de error.
"""
import json
from typing import Protocol, runtime_checkable


class AIError(Exception):
    """Fallo al llamar al proveedor de IA (HTTP, timeout, salida no válida…)."""


class AIHTTPError(AIError):
    """Respuesta HTTP no satisfactoria; `status` permite a los llamadores decidir."""

    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.status = status


class AIUnavailable(AIError):
    """Proveedor `none`, sin configurar (falta clave) o no instalado."""


@runtime_checkable
class Provider(Protocol):
    name: str

    def generate_text(self, prompt: str, system: str | None = None) -> str: ...

    def generate_json(self, prompt: str, schema: dict, system: str | None = None) -> dict: ...

    def check(self) -> tuple[bool, str]: ...


def extract_json(text: str, required: list[str] | None = None) -> dict:
    """Objeto JSON de `text` (tolera vallas y texto alrededor); `AIError` si no hay.

    Una respuesta que empieza por `[` (array) se rechaza. Si hay varios objetos, se prefiere el último
    que contenga todas las claves `required` (p. ej. un «{}» de ejemplo antes del objeto real).
    """
    text = text or ""
    head = text.strip().removeprefix("```json").removeprefix("```JSON").removeprefix("```").lstrip()
    if head.startswith("["):
        raise AIError("La IA devolvió un array JSON en lugar de un objeto")
    decoder = json.JSONDecoder()
    found: list[dict] = []
    i = 0
    while (i := text.find("{", i)) != -1:
        try:
            obj, end = decoder.raw_decode(text, i)
        except ValueError:
            i += 1
            continue
        if isinstance(obj, dict):
            found.append(obj)
        i = end
    if not found:
        raise AIError("La respuesta de la IA no contiene un objeto JSON válido")
    for obj in reversed(found):
        if all(k in obj for k in required or []):
            return obj
    return found[-1]


def build_json_prompt(prompt: str, schema: dict) -> str:
    """Prompt con el esquema embebido y la instrucción de responder solo con JSON."""
    return (
        f"{prompt}\n\n"
        "Responde ÚNICAMENTE con un objeto JSON válido (sin texto adicional) que cumpla este esquema:\n"
        f"{json.dumps(schema, ensure_ascii=False)}"
    )


def validate_required(data: dict, schema: dict) -> dict:
    """Comprueba las claves `required` de primer nivel; `AIError` si falta alguna."""
    missing = [k for k in schema.get("required", []) if k not in data]
    if missing:
        raise AIError(f"Faltan claves en el JSON de la IA: {', '.join(missing)}")
    return data


class BaseProvider:
    """Implementa `generate_json` sobre `_complete`, que cada proveedor define."""

    name = "base"

    def _complete(self, prompt: str, system: str | None, json_mode: bool) -> str:
        raise NotImplementedError

    def generate_text(self, prompt: str, system: str | None = None) -> str:
        return self._complete(prompt, system, False)

    def generate_json(self, prompt: str, schema: dict, system: str | None = None) -> dict:
        raw = self._complete(build_json_prompt(prompt, schema), system, True)
        return validate_required(extract_json(raw, schema.get("required", [])), schema)

    def check(self) -> tuple[bool, str]:
        raise NotImplementedError


class NoneProvider(BaseProvider):
    """Proveedor `none`: la app funciona sin IA (formulario manual, cartas con plantilla)."""

    name = "none"

    def _complete(self, prompt, system, json_mode):
        raise AIUnavailable("La IA está desactivada (proveedor «none»)")

    def check(self) -> tuple[bool, str]:
        return False, "IA desactivada"
