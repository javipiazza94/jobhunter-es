"""
search_config.py — Esquema y carga de la configuración de búsqueda (`JH_HOME/jobhunter.yaml`).

Si el usuario no tiene `jobhunter.yaml`, se usa `backend/defaults/jobhunter.yaml` (genérico).
Un fichero roto lanza `ConfigError` con la ruta y el campo, para fallar al arrancar y no a mitad de un scraping.
"""
import logging
import re
import unicodedata
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from config import JH_HOME

DEFAULT_CONFIG_PATH = Path(__file__).parent / "defaults" / "jobhunter.yaml"
USER_CONFIG_NAME = "jobhunter.yaml"
RESERVED_TRACK_IDS = {"manual_review"}
_WEIGHT_TOLERANCE = 1e-6
_TRACK_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """jobhunter.yaml ilegible o inválido; el mensaje incluye la ruta y el campo."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _check_sum_to_one(weights: list[float], what: str) -> None:
    total = sum(weights)
    if abs(total - 1.0) > _WEIGHT_TOLERANCE:
        raise ValueError(f"los pesos de {what} deben sumar 1.0 (suman {total:.4g})")


def _check_regex(value: str) -> str:
    try:
        re.compile(value, re.IGNORECASE)
    except re.error as exc:
        raise ValueError(f"expresión regular inválida: {exc}") from exc
    return value


def _lower_all(values: list[str]) -> list[str]:
    """Las listas que se comparan contra texto de ofertas (ya en minúsculas) se normalizan al cargar."""
    return [v.strip().lower() for v in values]


def _merge_over_defaults(value: dict[str, float], defaults: dict[str, float], what: str) -> dict[str, float]:
    extra = sorted(set(value) - set(defaults))
    if extra:
        raise ValueError(f"claves desconocidas en {what}: {', '.join(extra)} (válidas: {', '.join(defaults)})")
    return {**defaults, **value}


class KeywordGroup(_Model):
    id: str
    weight: float = Field(ge=0)
    keywords: list[str]


class LocationRule(_Model):
    weight: float = Field(ge=0)
    city: str | None = None
    area: list[str] = []
    remote_score: float = 1.0
    city_score: float = 1.0
    hybrid_score: float = 0.7
    other_score: float = 0.6
    unknown_score: float = 0.5


_EXPERIENCE_DEFAULT_SCORES = {"junior": 1.0, "mid": 0.5, "senior": 0.0, "lead": 0.0, "unknown": 0.5}


class ExperienceRule(_Model):
    weight: float = Field(ge=0)
    scores: dict[str, float] = dict(_EXPERIENCE_DEFAULT_SCORES)

    @model_validator(mode="before")
    @classmethod
    def _drop_obsolete_priority_max_years(cls, data):
        # Campo retirado: nada lo consumía. Se tolera en ficheros antiguos para no romperlos.
        if isinstance(data, dict) and "priority_max_years" in data:
            logger.warning("jobhunter.yaml: scoring.experience.priority_max_years está obsoleto y se ignora; "
                           "bórralo del fichero")
            data = {k: v for k, v in data.items() if k != "priority_max_years"}
        return data

    @field_validator("scores")
    @classmethod
    def _merge_scores_over_defaults(cls, value: dict[str, float]) -> dict[str, float]:
        extra = sorted(set(value) - set(_EXPERIENCE_DEFAULT_SCORES))
        if extra:
            raise ValueError(
                f"niveles de experiencia desconocidos: {', '.join(extra)} "
                f"(válidos: {', '.join(_EXPERIENCE_DEFAULT_SCORES)})"
            )
        return {**_EXPERIENCE_DEFAULT_SCORES, **value}


class SalaryRule(_Model):
    weight: float = Field(ge=0)
    min_base: int = 0
    max_only_score: float = 0.5
    unknown_score: float = 0.5


class Scoring(_Model):
    min_relevance: float = 0.55
    detail_fetch_min_score: float = 0.30
    profile_confidence_threshold: float = 0.2
    keyword_groups: list[KeywordGroup]
    location: LocationRule
    experience: ExperienceRule
    salary: SalaryRule
    negative_keywords: list[str] = []
    negative_title_keywords: list[str] = []

    @model_validator(mode="after")
    def _weights_sum_to_one(self):
        ids = [g.id for g in self.keyword_groups]
        dup = sorted({i for i in ids if ids.count(i) > 1})
        if dup:
            raise ValueError(f"id de keyword_groups repetido: {', '.join(dup)}")
        weights = [g.weight for g in self.keyword_groups]
        weights += [self.location.weight, self.experience.weight, self.salary.weight]
        _check_sum_to_one(weights, "scoring (grupos de keywords, location, experience y salary)")
        return self


class TagPattern(_Model):
    tag: str
    regex: str

    @field_validator("regex")
    @classmethod
    def _valid_regex(cls, value: str) -> str:
        return _check_regex(value)


class TrackCV(_Model):
    default: str | None = None
    by_tag: dict[str, str] = {}
    tag_aliases: dict[str, str | None] = {}
    tag_patterns: list[TagPattern] = []


class FollowedCompany(_Model):
    name: str
    tier: int = 1


_LOCATION_DEFAULT_SCORES = {"capital": 1.0, "nationwide": 0.8, "province": 0.7, "unknown": 0.5}
_SALARY_DEFAULT_SCORES = {"above": 1.0, "below": 0.3, "unknown": 0.5}
_WEIGHT_DEFAULTS = {"role": 0.40, "location": 0.25, "experience": 0.15, "salary": 0.05, "recency": 0.15}


class IsolatedRules(_Model):
    """Reglas del track aislado (trabajo puente). Las regex se compilan con re.IGNORECASE en su consumidor."""

    min_score: float = 0.40
    role_families: dict[str, list[str]]
    exclude_title_regex: str = ""
    exclude_text_regex: str = ""
    exclude_lang_regex: str = ""
    capital_names: list[str] = []
    province_regex: str = ""
    province_towns: list[str] = []
    remote_regex: str = ""
    nationwide_regex: str = ""
    location_scores: dict[str, float] = dict(_LOCATION_DEFAULT_SCORES)
    reject_levels: list[str] = ["senior", "lead", "mid"]
    unknown_level_score: float = 0.6
    salary_floor: int = 16000
    salary_scores: dict[str, float] = dict(_SALARY_DEFAULT_SCORES)
    weights: dict[str, float] = dict(_WEIGHT_DEFAULTS)
    recency: list[tuple[int, float]] = [(14, 1.0), (30, 0.7), (60, 0.3)]

    @field_validator(
        "exclude_title_regex", "exclude_text_regex", "exclude_lang_regex",
        "province_regex", "remote_regex", "nationwide_regex",
    )
    @classmethod
    def _valid_regex(cls, value: str) -> str:
        return _check_regex(value)

    @field_validator("capital_names", "province_towns", "reject_levels")
    @classmethod
    def _lowercase(cls, value: list[str]) -> list[str]:
        return _lower_all(value)

    @field_validator("role_families")
    @classmethod
    def _lowercase_role_families(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        return {family: _lower_all(words) for family, words in value.items()}

    @field_validator("location_scores")
    @classmethod
    def _merge_location_scores(cls, value: dict[str, float]) -> dict[str, float]:
        return _merge_over_defaults(value, _LOCATION_DEFAULT_SCORES, "isolated.location_scores")

    @field_validator("salary_scores")
    @classmethod
    def _merge_salary_scores(cls, value: dict[str, float]) -> dict[str, float]:
        return _merge_over_defaults(value, _SALARY_DEFAULT_SCORES, "isolated.salary_scores")

    @field_validator("weights")
    @classmethod
    def _merge_weights(cls, value: dict[str, float]) -> dict[str, float]:
        merged = _merge_over_defaults(value, _WEIGHT_DEFAULTS, "isolated.weights")
        negative = sorted(k for k, v in merged.items() if v < 0)
        if negative:
            raise ValueError(f"los pesos de isolated.weights no pueden ser negativos: {', '.join(negative)}")
        return merged

    @field_validator("recency")
    @classmethod
    def _sorted_recency(cls, value: list[tuple[int, float]]) -> list[tuple[int, float]]:
        if not value:
            raise ValueError("isolated.recency no puede estar vacía (lista de [días, puntuación])")
        return sorted(value, key=lambda pair: pair[0])

    @model_validator(mode="after")
    def _weights_sum_to_one(self):
        _check_sum_to_one(list(self.weights.values()), "isolated.weights")
        return self


class Track(_Model):
    id: str
    label: dict[str, str]
    kind: Literal["standard", "isolated"] = "standard"
    classify_keywords: list[str] = []
    search_keywords: list[str] = []
    remote_search_keywords: list[str] = []  # solo tracks aislados: búsquedas «<kw> teletrabajo»
    cv: TrackCV = TrackCV()
    cover_template: str = "tech"
    cover_letter_docx_key: str | None = None
    summary_key: str | None = None
    followed_companies: list[FollowedCompany] = []
    isolated: IsolatedRules | None = None

    @field_validator("classify_keywords")
    @classmethod
    def _lowercase_classify(cls, value: list[str]) -> list[str]:
        return _lower_all(value)  # se comparan con el texto de la oferta en minúsculas; search_keywords no

    @model_validator(mode="after")
    def _isolated_needs_rules(self):
        if self.kind == "isolated" and self.isolated is None:
            raise ValueError(f"el track aislado '{self.id}' necesita la sección 'isolated' con sus reglas")
        return self


class JobHunterConfig(_Model):
    scoring: Scoring
    tracks: list[Track]
    sources: dict[str, dict] = {}

    @field_validator("tracks")
    @classmethod
    def _valid_track_ids(cls, tracks: list[Track]) -> list[Track]:
        seen: set[str] = set()
        for t in tracks:
            if not _TRACK_ID_RE.fullmatch(t.id):
                raise ValueError(
                    f"id de track inválido: '{t.id}' (debe cumplir {_TRACK_ID_RE.pattern}: minúsculas, dígitos y _, empezando por letra)"
                )
            if t.id in RESERVED_TRACK_IDS:
                raise ValueError(f"el id de track '{t.id}' está reservado por el sistema")
            if t.id in seen:
                raise ValueError(f"id de track repetido: '{t.id}'")
            seen.add(t.id)
        return tracks

    def standard_tracks(self) -> list[Track]:
        return [t for t in self.tracks if t.kind == "standard"]

    def isolated_tracks(self) -> list[Track]:
        return [t for t in self.tracks if t.kind == "isolated"]

    def track(self, id: str) -> Track | None:
        return next((t for t in self.tracks if t.id == id), None)


def _format_errors(path: Path, exc: ValidationError) -> str:
    lines = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(raíz)"
        lines.append(f"  - {loc}: {err['msg']}")
    return f"Configuración inválida en {path}:\n" + "\n".join(lines)


def load_config(path: Path | None = None) -> JobHunterConfig:
    """Carga y valida; sin `path`: `JH_HOME/jobhunter.yaml` si existe, si no los valores por defecto."""
    path = Path(path) if path is not None else _active_path()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"No se puede leer la configuración {path} (¿UTF-8?): {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML inválido en {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"Configuración inválida en {path}: se esperaba un mapa con 'scoring' y 'tracks'")
    try:
        return JobHunterConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(_format_errors(path, exc)) from exc


def _active_path() -> Path:
    user_path = JH_HOME / USER_CONFIG_NAME
    return user_path if user_path.exists() else DEFAULT_CONFIG_PATH


def _stamp(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return st.st_mtime_ns, st.st_size


_cache: JobHunterConfig | None = None
_pinned = False  # set_config(cfg) fija una config (tests) y desactiva la recarga
_loaded_from: tuple[Path, tuple[int, int] | None] | None = None  # (fichero, huella) de la última lectura


def get_config() -> JobHunterConfig:
    """Config activa. Si el fichero de origen cambió desde la última lectura, se recarga; si el nuevo
    contenido es inválido se conserva la última config válida y se registra el error (una vez por versión)."""
    global _cache, _loaded_from
    if _pinned and _cache is not None:
        return _cache
    path = _active_path()
    source = (path, _stamp(path))
    if _cache is not None and source == _loaded_from:
        return _cache
    try:
        _cache = load_config(path)
    except ConfigError as exc:
        if _cache is None:
            raise
        logger.error("jobhunter.yaml cambió pero no es válido; conservando la última configuración válida.\n%s", exc)
    _loaded_from = source
    return _cache


def source_settings(source_id: str, cfg: JobHunterConfig | None = None) -> dict:
    """Parámetros de búsqueda de una fuente (`sources.<id>` del yaml); `{}` si no está configurada."""
    return (cfg or get_config()).sources.get(source_id, {})


def set_config(cfg: JobHunterConfig | None) -> None:
    """Para tests: fija la configuración (sin recarga automática); `None` la limpia y reactiva la recarga."""
    global _cache, _pinned, _loaded_from
    _cache = cfg
    _pinned = cfg is not None
    _loaded_from = None


def reload_config() -> JobHunterConfig:
    set_config(None)
    return get_config()


_COMPANY_NOISE = {"sa", "sl", "slu", "sau", "spain", "espana", "iberia", "group", "grupo", "inc", "ltd", "gmbh"}


def normalize_company(name: str) -> str:
    """Nombre comparable: minúsculas, sin acentos ni puntuación y sin sufijos legales/geográficos."""
    text = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    tokens = re.sub(r"[^a-z0-9]+", " ", text.replace(".", "")).split()  # «S.L.» -> «sl»
    while len(tokens) > 1 and tokens[-1] in _COMPANY_NOISE:
        tokens.pop()
    return " ".join(tokens)


def followed_tier_for(company: str, track_id: str | None, cfg: JobHunterConfig | None = None) -> int | None:
    """Mejor tier (el más bajo) de la empresa en las empresas seguidas del track; si no, en las de todos."""
    cfg = cfg or get_config()
    key = normalize_company(company)
    if not key:
        return None

    def best(tracks: list[Track]) -> int | None:
        tiers = [fc.tier for t in tracks for fc in t.followed_companies if normalize_company(fc.name) == key]
        return min(tiers) if tiers else None

    track = cfg.track(track_id) if track_id else None
    in_track = best([track]) if track else None
    return in_track if in_track is not None else best(cfg.tracks)
