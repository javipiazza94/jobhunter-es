"""
setup_builder.py — Asistente de primer arranque: convierte las respuestas del usuario en `profile.json` y
`jobhunter.yaml`.

Lógica pura (sin red ni IA): cada objetivo profesional es un track estándar, las herramientas del usuario son un
grupo de keywords más, los idiomas alimentan el `language_gate` y las fuentes elegidas reciben las keywords de
los objetivos. Los pesos de location/experience/salary salen de la configuración base (`defaults/jobhunter.yaml`)
y los grupos de keywords se reparten el resto a partes iguales, sumando exactamente 1.0.
"""
import re
import unicodedata
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from automation.language_gate import LANGUAGES, canonical_language
from automation.profile_proposal import ProfileDraft, draft_from_dict
from profile_store import load_profile, save_profile
import search_config
from scraper import sources as source_registry
from search_config import (
    DEFAULT_CONFIG_PATH,
    RESERVED_TRACK_IDS,
    AISettings,
    ConfigError,
    EmailSettings,
    FollowedCompany,
    JobHunterConfig,
    KeywordGroup,
    Track,
    TrackCV,
    load_config,
    save_config,
)

TOOLS_GROUP_ID = "tools"
_FALLBACK_ID = "target"
_MODALITY_ES = {"remote": "remoto", "hybrid": "híbrido", "onsite": "presencial"}
_LINKEDIN_SEARCHES_PER_TRACK = 3
# País (nombre es/en sin tildes, o código) → código ISO que entiende eligibility_gate.
_COUNTRY_CODES = {
    "ES": ("espana", "spain", "es"),
    "MX": ("mexico", "mx"),
    "CO": ("colombia", "co"),
    "AR": ("argentina", "ar"),
    "PE": ("peru", "pe"),
    "CL": ("chile", "cl"),
    "US": ("estados unidos", "united states", "usa", "us", "eeuu", "ee uu"),
    "GB": ("reino unido", "united kingdom", "uk", "gb", "great britain"),
    "DE": ("alemania", "germany", "deutschland", "de"),
    "FR": ("francia", "france", "fr"),
    "IT": ("italia", "italy", "it"),
    "PT": ("portugal", "pt"),
}
# Calibración del umbral de relevancia
_GOOD_MATCH_FACTOR = 0.85
_MIN_THRESHOLD = 0.2
_UNRELATED_MARGIN = 0.05
_UNRELATED_TITLES = ("Camarero", "Conductor de autobús", "Auxiliar de enfermería", "Albañil")
# CV subido por el asistente: siempre un fichero (nombre ya saneado) directamente dentro de JH_HOME/cv.
_CV_PATH_RE = re.compile(r"^cv/[A-Za-z0-9_-][A-Za-z0-9._-]*$")


class SetupAnswers(BaseModel):
    """Respuestas del asistente (pasos 2 y 3): borrador de perfil revisado y dónde buscar."""

    draft: ProfileDraft
    markets: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    acknowledged_sources: list[str] = Field(default_factory=list)
    followed_companies: list[str] = Field(default_factory=list)
    ai: AISettings = Field(default_factory=AISettings)
    ui_language: Literal["es", "en"] = "es"
    cv_path: str | None = None  # ruta relativa a JH_HOME devuelta por POST /api/setup/cv

    @field_validator("cv_path")
    @classmethod
    def _cv_path_inside_cv_dir(cls, value: str | None) -> str | None:
        if value is not None and not _CV_PATH_RE.match(value):
            raise ValueError("cv_path debe ser un fichero dentro de cv/ (p. ej. 'cv/mi_cv.pdf')")
        return value


# ── Mercados y fuentes ──────────────────────────────────────────────────────────


_MARKET_SOURCE_KEYS = ("id", "label", "requires_ack", "default_on")


def load_markets() -> dict[str, list[dict]]:
    """Mercados → fuentes sugeridas `[{id, label, requires_ack, default_on}]`, generado del registro de fuentes
    (scraper/sources; antes defaults/markets.yaml). Copia: se puede modificar."""
    return {m: [{k: s[k] for k in _MARKET_SOURCE_KEYS} for s in sources]
            for m, sources in source_registry.market_catalog("es").items()}


def source_catalog() -> dict[str, dict]:
    """Fuentes conocidas por el asistente (id → ficha): las del registro que se sugieren en algún mercado; una
    fuente es `requires_ack` si lo es en algún mercado."""
    catalog: dict[str, dict] = {}
    for sources in load_markets().values():
        for s in sources:
            entry = catalog.setdefault(s["id"], dict(s))
            entry["requires_ack"] = bool(entry.get("requires_ack")) or bool(s.get("requires_ack"))
    return catalog


# ── Utilidades ──────────────────────────────────────────────────────────────────


def _clean(values: list[str]) -> list[str]:
    """Sin vacíos ni duplicados (sin distinguir mayúsculas), conservando el orden."""
    out, seen = [], set()
    for v in values:
        v = (v or "").strip()
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return out


def slugify(text: str) -> str:
    """Id ASCII `[a-z][a-z0-9_]*` a partir de un título; `""` si no queda nada aprovechable."""
    ascii_text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_text).strip("_")
    if slug and not slug[0].isalpha():
        slug = f"t_{slug}"
    return slug


def _unique_id(base: str, taken: set[str]) -> str:
    candidate, n = base, 2
    while candidate in taken:
        candidate = f"{base}_{n}"
        n += 1
    taken.add(candidate)
    return candidate


def _targets(draft: ProfileDraft) -> list[tuple[str, list[str]]]:
    """(etiqueta, keywords) por objetivo útil. Sin keywords se busca por el título; sin nada, se descarta."""
    out = []
    for target in draft.targets:
        title = (target.title or "").strip()
        keywords = _clean(target.keywords) or ([title] if title else [])
        if not keywords:
            continue
        out.append((title or ", ".join(keywords[:3]), keywords))
    return out


# ── Perfil ──────────────────────────────────────────────────────────────────────


def country_code(name: str) -> str:
    """Código ISO de un país conocido (nombre es/en o código); `""` si no se reconoce."""
    key = re.sub(r"[^a-z ]+", " ", unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower())
    key = " ".join(key.split())
    return next((code for code, names in _COUNTRY_CODES.items() if key in names), "")


def _spain_work_permit(countries: list[str]) -> bool | None:
    """`personal.work_permit` tal como lo lee eligibility_gate (permiso para trabajar en España): True si
    España está en la lista, False si la lista tiene otros países, None si no se declaró nada."""
    cleaned = _clean(countries)
    if not cleaned:
        return None
    return any(country_code(c) == "ES" for c in cleaned)


def _profile_language(name: str) -> str:
    """Nombre canónico en español que entiende el language_gate («English» → «Inglés»); si no, el original."""
    canon = canonical_language(name)
    return canon.capitalize() if canon in LANGUAGES else name.strip()


def normalize_profile(profile: dict) -> dict:
    """Recalcula los campos derivados igual que el asistente (para PUT /api/profile, p. ej. al editar país o
    idiomas en Perfil): `personal.country_code` desde `personal.country` (un código puesto a mano para un país
    que no conocemos se conserva), `personal.work_permit` desde la lista de países con permiso y los nombres
    de idioma al canónico que entiende el language_gate. Devuelve una copia."""
    out = dict(profile)
    personal = profile.get("personal")
    if isinstance(personal, dict):
        personal = dict(personal)
        if "country" in personal:
            code = country_code(str(personal.get("country") or ""))
            previous = personal.get("country_code")
            blank = not str(personal.get("country") or "").strip()
            if not code and isinstance(previous, str) and previous and (blank or previous not in _COUNTRY_CODES):
                code = previous
            personal["country_code"] = code
        eligibility = profile.get("eligibility") if isinstance(profile.get("eligibility"), dict) else {}
        countries = personal.get("work_permit_countries") or eligibility.get("work_permit_countries")
        if isinstance(countries, list) and countries:
            personal["work_permit"] = _spain_work_permit([c for c in countries if isinstance(c, str)])
        out["personal"] = personal
    if isinstance(profile.get("languages"), list):
        out["languages"] = [
            {**lang, "language": _profile_language(lang["language"])}
            if isinstance(lang, dict) and isinstance(lang.get("language"), str) else lang
            for lang in profile["languages"]
        ]
    return out


def build_profile(answers: SetupAnswers) -> dict:
    """Perfil con la forma de `profile.example.json` (personal, idiomas, experiencia, stack, disponibilidad)
    más `eligibility` (permiso de trabajo, patrocinio de visado y carné de conducir)."""
    d = answers.draft
    names = d.full_name.split()
    eligibility = d.eligibility.model_dump()
    profile = {
        "personal": {
            "name": d.full_name.strip(),
            "short_name": " ".join(names[:2]),
            "first_name": names[0] if names else "",
            "last_name": " ".join(names[1:]),
            "email": d.email.strip(),
            "phone": d.phone.strip(),
            "city": d.city.strip(),
            "country": d.country.strip(),
            "country_code": country_code(d.country),
            "nationality": "",
            "work_permit": _spain_work_permit(d.eligibility.work_permit_countries),
            "work_permit_countries": _clean(d.eligibility.work_permit_countries),
            "driving_license": d.eligibility.driving_license,
        },
        "availability": {
            "work_mode_preference": ", ".join(_MODALITY_ES[m] for m in dict.fromkeys(d.modality)),
        },
        "salary_expectation": {"amount": None, "currency": "EUR", "period": "annual_gross"},
        "years_experience": d.years_experience,
        "stack": {"other_tools": _clean(d.tools)},
        "languages": [
            {"language": _profile_language(lang.language), "level": "Nativo" if lang.level == "native" else lang.level}
            for lang in d.languages
            if lang.language.strip()
        ],
        "experience": [e.model_dump() for e in d.experience],
        "targets": [{"title": label, "keywords": kws} for label, kws in _targets(d)],
        "eligibility": eligibility,
    }
    if answers.cv_path:
        profile["cv_path"] = answers.cv_path
    return profile


# Secciones que el asistente rellena solo en parte: se mezclan clave a clave con el perfil actual.
_MERGED_SECTIONS = ("personal", "availability", "stack", "eligibility")
# Claves que el asistente no pregunta (pone un valor vacío): solo se escriben si el perfil aún no las tiene.
_PLACEHOLDER_KEYS = {"personal": ("nationality",)}
_PLACEHOLDER_SECTIONS = ("salary_expectation",)


def _norm_key(*values) -> tuple[str, ...]:
    return tuple(str(v or "").strip().lower() for v in values)


def _merge_entries(old: list, new: list, key) -> list:
    """Lista nueva (manda el asistente), pero cada entrada conserva las claves extra de su gemela en `old`
    (misma `key`), p. ej. los logros de una experiencia que el asistente no muestra."""
    previous = {key(e): e for e in old if isinstance(e, dict)}
    return [{**previous.get(key(e), {}), **e} for e in new]


def merge_profile(current: dict, built: dict) -> dict:
    """Perfil del asistente aplicado sobre el actual sin perder nada que el asistente no pregunte.

    Se conservan las claves que el asistente no produce (resumen, cartas, otros CV, formación…). `personal`,
    `availability`, `stack` y `eligibility` se mezclan clave a clave (las listas que rellena el asistente, como
    `stack.other_tools`, se sustituyen). Experiencia e idiomas son los del asistente, pero cada entrada conserva
    las claves extra de la misma entrada en el perfil actual."""
    merged = dict(current)
    for key, value in built.items():
        old = current.get(key)
        if key in _MERGED_SECTIONS and isinstance(old, dict):
            section = {**old, **value}
            for placeholder in _PLACEHOLDER_KEYS.get(key, ()):
                if old.get(placeholder):
                    section[placeholder] = old[placeholder]
            merged[key] = section
        elif key in _PLACEHOLDER_SECTIONS and isinstance(old, dict):
            merged[key] = old
        elif key == "experience" and isinstance(old, list):
            merged[key] = _merge_entries(old, value, lambda e: _norm_key(e.get("company"), e.get("role")))
        elif key == "languages" and isinstance(old, list):
            merged[key] = _merge_entries(old, value, lambda e: _norm_key(canonical_language(str(e.get("language")))
                                                                            or e.get("language")))
        else:
            merged[key] = value
    return merged


# ── jobhunter.yaml ──────────────────────────────────────────────────────────────


def _split_weights(rest: float, n: int) -> list[float]:
    """`n` pesos iguales que suman exactamente `rest` (el último absorbe el redondeo)."""
    share = round(rest / n, 6)
    weights = [share] * (n - 1)
    return weights + [round(rest - sum(weights), 6)]


def _source_settings(source_id: str, keywords: list[str], tracks: list[Track], answers: SetupAnswers) -> dict:
    d = answers.draft
    city = d.city.strip()
    wants_remote = not d.modality or "remote" in d.modality
    wants_local = bool(city) and any(m in d.modality for m in ("hybrid", "onsite"))
    settings: dict = {"keywords": list(keywords)}
    if source_id == "tecnoempleo":
        settings["locations"] = (["remoto"] if wants_remote else []) + ([city] if wants_local else [])
    elif source_id == "indeed":
        settings["locations"] = (["Remoto"] if wants_remote else []) + ([city] if wants_local else [])
    elif source_id == "computrabajo" and wants_local:
        settings["location"] = city
    elif source_id == "linkedin":
        location = (city if wants_local else "") or d.country.strip() or "Remote"
        settings["searches"] = [
            {"keywords": kw, "location": location, "track": t.id}
            for t in tracks
            for kw in t.search_keywords[:_LINKEDIN_SEARCHES_PER_TRACK]
        ]
    return settings


def _merge_source(generated: dict, current: dict, owned_tracks: set[str], old_keywords: set[str]) -> dict:
    """Ajustes de una fuente que ya estaba activa: se conservan sus claves propias (p. ej. `max_pages`); lo que
    genera el asistente se regenera, sin perder las keywords añadidas a mano ni las búsquedas de LinkedIn de
    tracks que el asistente no gestiona (aislados)."""
    merged = {**current, **generated}
    if "keywords" in generated:
        extra = [k for k in current.get("keywords") or [] if isinstance(k, str) and k.lower() not in old_keywords]
        merged["keywords"] = _clean([*generated["keywords"], *extra])
    if "searches" in generated:
        kept = [s for s in current.get("searches") or [] if not (isinstance(s, dict) and s.get("track") in owned_tracks)]
        merged["searches"] = [*generated["searches"], *kept]
    return merged


def build_config(
    answers: SetupAnswers,
    base: JobHunterConfig | None = None,
    email: EmailSettings | None = None,
    current: JobHunterConfig | None = None,
) -> JobHunterConfig:
    """Config completa a partir de las respuestas. Lanza `ValueError` si no hay ningún objetivo útil.

    Primera vez (`current` None): parte de la config base (`defaults/jobhunter.yaml`). Al volver a pasar el
    asistente, `current` es el jobhunter.yaml del usuario y se conserva todo lo que el asistente no gestiona:
    tracks aislados, grupos de keywords propios, reglas de location/experience/salary y demás campos de
    `scoring`, y los ajustes propios de cada fuente. Se regeneran los tracks estándar, sus grupos de keywords
    (ids = ids de track + "tools"), los pesos de los grupos (a partes iguales), `location.city` y el umbral.

    `email` (por defecto la sección de `current`, si no la de la base) se conserva. El CV subido
    (`answers.cv_path`) es el CV por defecto de cada track."""
    targets = _targets(answers.draft)
    if not targets:
        raise ValueError("el asistente necesita al menos un objetivo profesional (título o keywords)")
    base = base or load_config(DEFAULT_CONFIG_PATH)
    origin = current or base
    old_standard = current.standard_tracks() if current else []
    isolated = current.isolated_tracks() if current else []

    followed = [FollowedCompany(name=name, tier=1) for name in _clean(answers.followed_companies)]
    owned_old = {t.id for t in old_standard} | {TOOLS_GROUP_ID}
    custom_groups = [g for g in origin.scoring.keyword_groups if current and g.id not in owned_old]
    taken = set(RESERVED_TRACK_IDS) | {TOOLS_GROUP_ID} | {t.id for t in isolated} | {g.id for g in custom_groups}
    tracks = [
        Track(
            id=_unique_id(slugify(label) or _FALLBACK_ID, taken),
            label={"es": label, "en": label},
            kind="standard",
            classify_keywords=keywords,
            search_keywords=keywords,
            followed_companies=[f.model_copy() for f in followed],
            cv=TrackCV(default=answers.cv_path),
        )
        for label, keywords in targets
    ]

    groups = [(t.id, [k.lower() for k in t.search_keywords]) for t in tracks]
    tools = [t.lower() for t in _clean(answers.draft.tools)]
    if tools:
        groups.append((TOOLS_GROUP_ID, tools))
    groups += [(g.id, list(g.keywords)) for g in custom_groups]
    s = origin.scoring
    rest = 1.0 - (s.location.weight + s.experience.weight + s.salary.weight)
    weights = _split_weights(rest, len(groups))
    scoring = s.model_copy(deep=True, update={
        "keyword_groups": [KeywordGroup(id=gid, weight=w, keywords=kws) for (gid, kws), w in zip(groups, weights)],
    })
    scoring.location.city = answers.draft.city.strip() or None
    scoring.eligibility_hard_reject = True  # el asistente activa los requisitos duros (instalaciones antiguas: no)

    union = _clean([kw for t in tracks for kw in t.search_keywords])
    catalog = source_catalog()
    acknowledged = set(answers.acknowledged_sources)
    previous = current.sources if current else {}
    owned_tracks = {t.id for t in old_standard} | {t.id for t in tracks}
    old_keywords = {kw.lower() for t in old_standard for kw in t.search_keywords}
    sources = {}
    for sid in dict.fromkeys(answers.sources):
        if sid not in catalog:
            if sid in previous:  # fuente añadida a mano al jobhunter.yaml: se queda tal cual
                sources[sid] = previous[sid]
            continue
        if catalog[sid]["requires_ack"] and sid not in acknowledged:
            continue
        generated = _source_settings(sid, union, tracks, answers)
        sources[sid] = (_merge_source(generated, previous[sid], owned_tracks, old_keywords)
                        if sid in previous else generated)

    cfg = JobHunterConfig.model_validate({
        "scoring": scoring.model_dump(),
        "tracks": [t.model_dump() for t in [*tracks, *isolated]],
        "sources": sources,
        "ai": answers.ai.model_dump(),
        "email": (email or origin.email).model_dump(),
    })
    # El umbral lo calibra siempre el asistente, con el de la config base como techo.
    cfg.scoring.min_relevance = _calibrate_min_relevance(cfg, answers.draft.city.strip(), base.scoring.min_relevance)
    return cfg


def _calibrate_min_relevance(cfg: JobHunterConfig, city: str, base_threshold: float) -> float:
    """Umbral de relevancia alcanzable con esta config.

    Con los pesos repartidos entre varios grupos, una oferta perfecta para UN objetivo no llega al umbral de la
    config base (0.55). Se puntúa una oferta «buena» sintética por track (título + hasta 3 de sus keywords, en
    la ciudad del usuario o en remoto, sin salario) y se toma la peor: umbral = 85 % de esa puntuación, acotado a
    [0.2, umbral base]. Una oferta sin relación (título ajeno, misma ciudad) tiene que quedar por debajo: si no,
    se sube el umbral a «sin relación + 0.05» sin pasar de la oferta buena."""
    from automation.filter_engine import keyword_hit, score_offer  # import tardío: evita ciclos

    location = city or "remoto"
    saved = (search_config._cache, search_config._pinned, search_config._loaded_from)
    search_config.set_config(cfg)  # el scoring y sus filtros leen la config activa
    try:
        good = min(
            score_offer({
                "title": t.label["es"],
                "description": " ".join(t.search_keywords[:3]),
                "location": location,
            }, cfg)
            for t in cfg.standard_tracks()
        )
        all_keywords = [kw for g in cfg.scoring.keyword_groups for kw in g.keywords]
        title = next((u for u in _UNRELATED_TITLES if not any(keyword_hit(kw, u.lower()) for kw in all_keywords)), None)
        unrelated = score_offer({"title": title, "description": "", "location": location}, cfg) if title else None
    finally:
        search_config._cache, search_config._pinned, search_config._loaded_from = saved

    threshold = min(max(round(_GOOD_MATCH_FACTOR * good, 2), _MIN_THRESHOLD), base_threshold)
    if unrelated is not None and unrelated >= threshold:
        threshold = min(round(unrelated + _UNRELATED_MARGIN, 3), good)
    if unrelated is not None and unrelated >= threshold:
        raise ValueError(
            f"no se puede separar una oferta buena ({good}) de una sin relación ({unrelated}) con esta configuración"
        )
    return threshold


def _current_config(path: Path) -> JobHunterConfig | None:
    """jobhunter.yaml del usuario (volver a pasar el asistente parte de él); None si no hay o no es válido."""
    if not path.is_file():
        return None
    try:
        return load_config(path)
    except ConfigError:
        return None


def apply_setup(answers: SetupAnswers) -> dict:
    """Escribe `profile.json` y `jobhunter.yaml` (atómicos). Si las respuestas no valen (`ValueError`) no se
    escribe nada. Al volver a pasar el asistente, ambos se mezclan con lo actual (ver `build_config` y
    `merge_profile`). Devuelve los ids de los tracks y las fuentes activadas."""
    path = search_config.user_config_path()
    cfg = build_config(answers, current=_current_config(path))
    profile = merge_profile(load_profile(), build_profile(answers))
    save_config(cfg, path)
    save_profile(profile)
    return {"tracks": [t.id for t in cfg.standard_tracks()], "sources": list(cfg.sources)}


# ── Volver a ejecutar el asistente y fuentes desde Perfil ───────────────────────────────────────


def _modality_from_profile(text: str) -> list[str]:
    words = {w.strip().lower() for w in (text or "").split(",")}
    return [m for m, es in _MODALITY_ES.items() if es in words]


def current_answers(cfg: JobHunterConfig | None = None, profile: dict | None = None) -> SetupAnswers:
    """Respuestas equivalentes a la configuración actual (perfil + jobhunter.yaml), para precargar el asistente.

    Los objetivos salen de los tracks estándar (título = etiqueta, keywords = classify_keywords); los mercados,
    de las fuentes activadas. Las fuentes `requires_ack` activadas cuentan como aceptadas (solo se activan así)."""
    cfg = cfg or search_config.get_config()
    profile = load_profile() if profile is None else profile
    personal = profile.get("personal") if isinstance(profile.get("personal"), dict) else {}
    availability = profile.get("availability") if isinstance(profile.get("availability"), dict) else {}
    stack = profile.get("stack") if isinstance(profile.get("stack"), dict) else {}
    tracks = [t for t in cfg.tracks if t.kind == "standard"]
    draft = draft_from_dict({
        "full_name": personal.get("name"),
        "email": personal.get("email"),
        "phone": personal.get("phone"),
        "city": personal.get("city"),
        "country": personal.get("country"),
        "targets": [
            {"title": t.label.get("es") or t.label.get("en") or t.id, "keywords": list(t.classify_keywords)} for t in tracks
        ],
        "years_experience": profile.get("years_experience"),
        "experience": profile.get("experience"),
        "tools": stack.get("other_tools"),
        "languages": profile.get("languages"),
        "modality": _modality_from_profile(str(availability.get("work_mode_preference") or "")),
        "eligibility": profile.get("eligibility"),
    })
    catalog = source_catalog()
    enabled = list(cfg.sources)
    markets = [m for m, sources in load_markets().items() if any(s["id"] in cfg.sources for s in sources)]
    followed = list(dict.fromkeys(fc.name for t in tracks for fc in t.followed_companies))
    cv_path = profile.get("cv_path") if isinstance(profile.get("cv_path"), str) else None
    return SetupAnswers(
        draft=draft,
        markets=markets,
        sources=enabled,
        acknowledged_sources=[s for s in enabled if catalog.get(s, {}).get("requires_ack")],
        followed_companies=followed,
        ai=cfg.ai,
        cv_path=cv_path if cv_path and _CV_PATH_RE.match(cv_path) else None,
    )


def sources_view(cfg: JobHunterConfig | None = None) -> list[dict]:
    """Fuentes del catálogo (y las que ya tenga el jobhunter.yaml aunque no estén en él) con su estado."""
    cfg = cfg or search_config.get_config()
    markets_of: dict[str, list[str]] = {}
    for market, sources in load_markets().items():
        for s in sources:
            markets_of.setdefault(s["id"], []).append(market)
    catalog = source_catalog()
    out = []
    for sid in [*catalog, *(s for s in cfg.sources if s not in catalog)]:
        entry = catalog.get(sid, {"label": sid, "requires_ack": False})
        enabled = sid in cfg.sources
        out.append({
            "id": sid,
            "label": entry["label"],
            "markets": markets_of.get(sid, []),
            "requires_ack": bool(entry["requires_ack"]),
            "enabled": enabled,
            "acknowledged": enabled and bool(entry["requires_ack"]),
        })
    return out


def update_sources(enabled: list[str], acknowledged: list[str], cfg: JobHunterConfig | None = None) -> JobHunterConfig:
    """Config con la sección `sources` reescrita. Las fuentes que siguen activas conservan sus ajustes; las nuevas
    reciben los del asistente (keywords de los tracks, ciudad y modalidad del perfil). Lanza `ValueError` si una
    fuente es desconocida o es `requires_ack` sin aceptar."""
    cfg = cfg or search_config.get_config()
    catalog = source_catalog()
    acked = set(acknowledged)
    for sid in enabled:
        if sid not in catalog and sid not in cfg.sources:
            raise ValueError(f"fuente desconocida: {sid}")
        if catalog.get(sid, {}).get("requires_ack") and sid not in acked:
            raise ValueError(f"la fuente {sid} requiere aceptar su aviso antes de activarla")
    answers = current_answers(cfg)
    tracks = [t for t in cfg.tracks if t.kind == "standard"]
    union = _clean([kw for t in tracks for kw in t.search_keywords])
    sources = {
        sid: cfg.sources[sid] if sid in cfg.sources else _source_settings(sid, union, tracks, answers)
        for sid in dict.fromkeys(enabled)
    }
    return cfg.model_copy(update={"sources": sources})
