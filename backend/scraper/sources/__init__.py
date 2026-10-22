"""scraper/sources — registro de fuentes de ofertas autodescubierto.

Cada módulo de este paquete (sin `_` delante) declara una fuente con una constante `SPEC` (`SourceSpec`): id,
etiqueta es/en, mercados del asistente, si requiere aceptar un aviso, si va marcada por defecto, sus parámetros
(`sources.<id>` de jobhunter.yaml), cómo atribuir la oferta y cómo ejecutarla (`run(RunContext)`). El runner, los
trabajos de la API, el asistente y Ajustes → Fuentes leen de aquí; añadir una fuente = un fichero + su test.

Los pasos que no son portales (`seed`, `contacts`, `generic`, `resolve-websites`, `linkedin-login`, inbox) siguen
en scraper/runner.py y scraper/jobs.py.
"""
from __future__ import annotations

import importlib
import inspect
import pkgutil
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Literal

MARKETS: tuple[str, ...] = ("spain", "latam", "remote", "global")
LANGS: tuple[str, ...] = ("es", "en")
_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class SourceError(Exception):
    """Fallo al consultar una fuente (HTTP no 200, JSON inválido o estructura inesperada)."""


@dataclass(frozen=True)
class Attribution:
    """Cómo citar el origen de una oferta: nombre del portal, su web (vacía si cada oferta es de una web distinta,
    p. ej. las webs de empresas) y si es obligatorio mostrarlo."""
    name: str
    url: str
    required: bool = False


@dataclass(frozen=True)
class ParamSpec:
    """Un parámetro de `sources.<id>` en jobhunter.yaml: tipo, valor por defecto y ayuda (es)."""
    type: str
    default: Any = None
    help: str = ""


@dataclass(frozen=True)
class RunContext:
    """Lo que recibe `SourceSpec.run`. `track_id` None = fuente suelta (CLI `--source`, trabajo de la API);
    con track, `keywords` son las `search_keywords` del track. `settings` = `sources.<id>` de jobhunter.yaml."""
    settings: dict
    keywords: list[str]
    track_id: str | None = None
    max_pages: int = 3
    dry_run: bool = False


@dataclass(frozen=True)
class SourceSpec:
    """Ficha de una fuente.

    - `markets`: mercados del asistente donde se sugiere (vacío = no aparece en el asistente).
    - `market_labels`: etiqueta distinta en un mercado concreto (p. ej. «Tecnoempleo (remoto)»).
    - `standalone`: se puede lanzar sola (`python -m scraper.jobs <id>`, API `source=<id>`, runner `--source`).
    - `track_pipeline`: forma parte del pipeline multi-portal de un track (`--track`).
    - `track_always`: en el pipeline de un track se ejecuta aunque no esté activada en `sources:`.
    - `persists_itself`: guarda ella misma lo que encuentra; `run` devuelve [] y no se pasa por persist.
    - `order`: orden en el catálogo, en los mercados y en el pipeline de un track.
    """
    id: str
    label: dict[str, str]
    run: Callable[[RunContext], Awaitable[list[dict]] | list[dict]]
    attribution: Attribution
    markets: tuple[str, ...] = ()
    requires_ack: bool = False
    default_on: bool = False
    kind: Literal["json", "html", "playwright"] = "html"
    start_url: str | None = None
    start_url_fn: Callable[[dict], str] | None = None
    params: dict[str, ParamSpec] = field(default_factory=dict)
    track_pipeline: bool = False
    requires_secret: str | None = None
    standalone: bool = True
    track_always: bool = False
    company_query: bool = False
    persists_itself: bool = False
    order: int = 1000
    market_labels: dict[str, dict[str, str]] = field(default_factory=dict)
    ack_warning: dict[str, str] = field(default_factory=dict)

    def start_url_for(self, settings: dict | None = None) -> str | None:
        """URL de inicio para comprobación de robots, parametrizable según `settings`."""
        if self.start_url_fn and settings:
            try:
                return self.start_url_fn(settings)
            except Exception:
                return self.start_url
        return self.start_url

    def label_for(self, lang: str = "es", market: str | None = None) -> str:
        """Etiqueta en `lang` (cae a es) y, si se indica, la propia del mercado."""
        labels = self.market_labels.get(market, self.label) if market else self.label
        return labels.get(lang) or labels.get("es") or self.id

    def warning_for(self, lang: str = "es") -> str:
        """Aviso legal en `lang` (cae a es si falta)."""
        return self.ack_warning.get(lang) or self.ack_warning.get("es") or ""


def validate(spec: SourceSpec) -> None:
    """Lanza `ValueError` si la ficha está incompleta o es incoherente."""
    if not isinstance(spec, SourceSpec):
        raise ValueError(f"SPEC no es un SourceSpec: {spec!r}")
    if not _ID_RE.match(spec.id):
        raise ValueError(f"id de fuente inválido: {spec.id!r} (minúsculas, dígitos y _)")
    for lang in LANGS:
        if not spec.label.get(lang):
            raise ValueError(f"fuente {spec.id}: falta la etiqueta en '{lang}'")
    for market, labels in spec.market_labels.items():
        if market not in spec.markets or any(not labels.get(lang) for lang in LANGS):
            raise ValueError(f"fuente {spec.id}: market_labels['{market}'] inválido")
    unknown = [m for m in spec.markets if m not in MARKETS]
    if unknown:
        raise ValueError(f"fuente {spec.id}: mercados desconocidos {unknown}")
    if not isinstance(spec.attribution, Attribution) or not spec.attribution.name:
        raise ValueError(f"fuente {spec.id}: falta la atribución (al menos el nombre)")
    if spec.requires_ack and spec.default_on:
        raise ValueError(f"fuente {spec.id}: una fuente con aviso no puede ir marcada por defecto")
    if spec.requires_ack and not spec.ack_warning.get("es"):
        raise ValueError(f"fuente {spec.id}: requires_ack=True pero falta ack_warning en español")
    if not callable(spec.run):
        raise ValueError(f"fuente {spec.id}: run no es invocable")


def discover(package: str = __name__) -> dict[str, SourceSpec]:
    """Importa los módulos del paquete y devuelve id → ficha, ordenado por (`order`, id). Ids únicos."""
    pkg = importlib.import_module(package)
    specs: dict[str, SourceSpec] = {}
    for info in pkgutil.iter_modules(pkg.__path__):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{package}.{info.name}")
        spec = getattr(module, "SPEC", None)
        if spec is None:
            raise ValueError(f"{package}.{info.name} no declara SPEC")
        validate(spec)
        if spec.id in specs:
            raise ValueError(f"id de fuente duplicado: {spec.id}")
        specs[spec.id] = spec
    return dict(sorted(specs.items(), key=lambda kv: (kv[1].order, kv[0])))


@lru_cache(maxsize=1)
def _registry() -> dict[str, SourceSpec]:
    return discover()


def registry() -> dict[str, SourceSpec]:
    """Fuentes registradas (id → ficha), en orden de catálogo."""
    return dict(_registry())


def reset_cache() -> None:
    """Vuelve a descubrir los módulos en la próxima llamada (tests)."""
    _registry.cache_clear()


def get(source_id: str) -> SourceSpec:
    """Ficha de una fuente; `KeyError` si no existe."""
    try:
        return _registry()[source_id]
    except KeyError:
        raise KeyError(f"fuente desconocida: {source_id}") from None


def standalone_ids() -> tuple[str, ...]:
    """Fuentes que se pueden lanzar solas (API, `scraper.jobs`, runner `--source`)."""
    return tuple(sid for sid, s in _registry().items() if s.standalone)


def track_pipeline() -> list[SourceSpec]:
    """Fuentes del pipeline multi-portal de un track, en orden."""
    return [s for s in _registry().values() if s.track_pipeline]


def market_catalog(lang: str = "es") -> dict[str, list[dict]]:
    """Mercado → fuentes sugeridas `[{id, label, requires_ack, default_on, attribution}]` (sustituye a markets.yaml)."""
    out: dict[str, list[dict]] = {}
    for market in MARKETS:
        out[market] = [
            {
                "id": s.id,
                "label": s.label_for(lang, market),
                "requires_ack": s.requires_ack,
                "ack_warning": s.warning_for(lang),
                "default_on": s.default_on,
                "attribution": {"name": s.attribution.name, "url": s.attribution.url,
                                "required": s.attribution.required},
            }
            for s in _registry().values() if market in s.markets
        ]
    return out


async def execute(spec: SourceSpec, ctx: RunContext) -> list[dict]:
    """Ejecuta `spec.run(ctx)`, sea síncrona o asíncrona."""
    result = spec.run(ctx)
    if inspect.isawaitable(result):
        result = await result
    return list(result or [])
